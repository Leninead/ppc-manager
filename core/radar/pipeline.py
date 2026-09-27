"""One Radar Amazon run: fetch, verify, ask the agent to group and write, validate its answer, save.

The AI only groups and writes. Which items exist, which passed the checks and how confident each topic is are
decided here, in code, so a topic can never cite an item nobody verified nor label itself official.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from ai.agent_call import build_agent_call
from ai.agents.radar.context import MAX_TOPICS, RadarData, item_ids
from core.radar.feeds import RawItem, fetch_feed
from core.radar.sources import SOURCES
from core.radar.verify import (
    MAX_ITEMS_PER_RUN,
    cap_items,
    check_link,
    week_start,
    with_truncated_text,
    within_window,
)

log = logging.getLogger("radar.pipeline")

AGENT_SLUG = "radar"
CONFIDENCE_OFFICIAL = "official"
CONFIDENCE_CONFIRMED = "confirmed"
CONFIDENCE_EXPERT = "expert"


class RadarError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedItem:
    item: RawItem
    source: dict
    verified_at: datetime
    http_status: int

    @property
    def published_at(self) -> datetime:
        return self.item.published_at


@dataclass
class SourceReport:
    source_id: str
    fetched: int = 0
    in_window: int = 0
    link_ok: int = 0
    sent: int = 0


@dataclass
class RunResult:
    week_start: str
    report: list[SourceReport]
    items: list[VerifiedItem]
    rows: list[dict] = field(default_factory=list)
    dropped_topics: int = 0


def run(now: datetime, *, http_get: Callable, ai_ask: Callable | None = None,
        save: Callable[[list[dict]], None] | None = None, sources: tuple[dict, ...] = SOURCES) -> RunResult:
    """Without `ai_ask` it stops after verification (dry run); without `save` nothing is written."""
    report = {source["id"]: SourceReport(source["id"]) for source in sources}
    verified = _verified_items(now, http_get, sources, report)
    result = RunResult(week_start=week_start(now).isoformat(), report=list(report.values()), items=verified)
    if ai_ask is None or not verified:
        return result

    call = build_agent_call(AGENT_SLUG, _agent_data(result.week_start, verified))
    response = ai_ask(**call.call)
    answer = response.get("structured_output")
    if not isinstance(answer, dict):
        raise RadarError("La IA no devolvió el formato pactado.")
    by_id = dict(zip(item_ids(len(verified)), verified))
    topics, dropped = _valid_topics(answer.get("topics") or [], by_id)
    result.dropped_topics = dropped
    result.rows = [_row(topic, rank, result.week_start, now, call, response)
                   for rank, topic in enumerate(topics, start=1)]
    if save is not None and result.rows:
        save(result.rows)
    return result


def confidence(items: list[VerifiedItem]) -> str:
    official = [entry.source["is_official"] for entry in items]
    if all(official):
        return CONFIDENCE_OFFICIAL
    if any(official):
        return CONFIDENCE_CONFIRMED
    return CONFIDENCE_EXPERT


def _verified_items(now: datetime, http_get: Callable, sources: tuple[dict, ...],
                    report: dict[str, SourceReport]) -> list[VerifiedItem]:
    candidates: list[tuple[RawItem, dict]] = []
    for source in sources:
        items = fetch_feed(source, http_get=http_get)
        report[source["id"]].fetched = len(items)
        for item in items:
            if within_window(item, now):
                report[source["id"]].in_window += 1
                candidates.append((item, source))

    link_status: dict[str, tuple[bool, int | None]] = {}
    verified_at: dict[str, datetime] = {}
    passed: list[VerifiedItem] = []
    seen_links: set[str] = set()
    for item, source in candidates:
        if item.link not in link_status:
            link_status[item.link] = check_link(item.link, http_get)
            verified_at[item.link] = datetime.now(timezone.utc)
        ok, status = link_status[item.link]
        if not ok:
            log.info("radar: %s dropped, link %s answered %s", source["id"], item.link, status)
            continue
        # The same article reached through two feeds is one item; a shared fallback page is not a duplicate.
        if item.link != source["fallback_link"]:
            if item.link in seen_links:
                continue
            seen_links.add(item.link)
        report[source["id"]].link_ok += 1
        passed.append(VerifiedItem(item, source, verified_at[item.link], status))

    # Amazon's own items always go; the experts share whatever room the cap leaves.
    official = [entry for entry in passed if entry.source["is_official"]]
    experts = [entry for entry in passed if not entry.source["is_official"]]
    chosen = cap_items(official + cap_items(experts, max(0, MAX_ITEMS_PER_RUN - len(official))), len(passed))
    kept = [replace(entry, item=with_truncated_text(entry.item)) for entry in chosen]
    for entry in kept:
        report[entry.source["id"]].sent += 1
    return kept


def _agent_data(week: str, verified: list[VerifiedItem]) -> RadarData:
    return RadarData(week_label=f"semana del {week}", items=[
        {"source": entry.source["name"], "person": entry.source["person"],
         "is_official": entry.source["is_official"], "published": entry.item.published_at.date().isoformat(),
         "title": entry.item.title, "text": entry.item.text}
        for entry in verified
    ])


def _valid_topics(topics: list, by_id: dict[str, VerifiedItem]) -> tuple[list[dict], int]:
    """Topics citing only items that exist, each with a primary link no other topic uses, best rank first."""
    ordered = sorted((topic for topic in topics if isinstance(topic, dict)),
                     key=lambda topic: topic.get("rank") if isinstance(topic.get("rank"), int) else 10 ** 6)
    kept: list[dict] = []
    used_links: set[str] = set()
    dropped = len(topics) - len(ordered)
    for topic in ordered:
        cited = list(dict.fromkeys(topic.get("item_ids") or []))
        texts = [str(topic.get(name) or "").strip() for name in ("title_es", "summary_es", "implications_es")]
        if not cited or any(item_id not in by_id for item_id in cited) or not all(texts) \
                or len(kept) == MAX_TOPICS:
            log.info("radar: topic %r dropped (cites %s)", topic.get("title_es"), cited)
            dropped += 1
            continue
        entries = [by_id[item_id] for item_id in cited]
        primary = _primary(entries, used_links)
        if primary is None:
            dropped += 1
            continue
        used_links.add(primary.item.link)
        kept.append({"title_es": texts[0], "summary_es": texts[1], "implications_es": texts[2],
                     "entries": entries, "primary": primary})
    return kept, dropped


def _primary(entries: list[VerifiedItem], used_links: set[str]) -> VerifiedItem | None:
    """Amazon's own item first, then an item with its own page, newest first."""
    preferred = sorted(entries, key=lambda entry: (not entry.source["is_official"],
                                                    entry.item.link == entry.source["fallback_link"],
                                                    -entry.item.published_at.timestamp()))
    return next((entry for entry in preferred if entry.item.link not in used_links), None)


def _row(topic: dict, rank: int, week: str, now: datetime, call, response: dict) -> dict:
    entries: list[VerifiedItem] = topic["entries"]
    primary: VerifiedItem = topic["primary"]
    return {
        "week_start": week,
        "title_es": topic["title_es"],
        "summary_es": topic["summary_es"],
        "implications_es": topic["implications_es"],
        "confidence": confidence(entries),
        "sources": [_source_entry(entry) for entry in entries],
        "primary_link": primary.item.link,
        "primary_published_at": primary.item.published_at.isoformat(),
        "rank": rank,
        "input_digest": call.input_digest,
        "agent_version": call.agent_version,
        "model": call.model,
        "usage": response.get("usage") or {},
        # Every row of a run shares it: that is how the home tells this run from an earlier one of the same week.
        "created_at": now.isoformat(),
    }


def _source_entry(entry: VerifiedItem) -> dict:
    return {
        "source_id": entry.source["id"],
        "name": entry.source["name"],
        "person": entry.source["person"],
        "title": entry.item.title,
        "link": entry.item.link,
        "published_at": entry.item.published_at.isoformat(),
        "verified_at": entry.verified_at.isoformat(),
        "http_status": entry.http_status,
        "is_official": entry.source["is_official"],
    }

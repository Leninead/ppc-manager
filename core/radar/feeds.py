"""Reads RSS 2.0 and Atom feeds into RawItem, with the standard library only.

Tolerant on purpose: the Amazon Ads API feed declares US-ASCII and ships UTF-8, and podcast feeds carry HTML
entities XML does not define. A feed that still cannot be read is logged and skipped; it never stops a run.
"""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.entities import name2codepoint

import requests

log = logging.getLogger("radar.feeds")

FETCH_TIMEOUT_S = 30
USER_AGENT = "Mozilla/5.0 (compatible; CapybarasRadar/1.0; RSS reader)"
_XML_ENTITIES = frozenset({"amp", "lt", "gt", "quot", "apos"})
_XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>")
_NAMED_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_BARE_AMPERSAND = re.compile(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_BLOCK_TAG = re.compile(r"<(br|/p|/li|/div|/h\d)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
# Publication dates only: Atom's <updated> moves on every edit and would let an old item into the window.
_DATE_TAGS = ("published", "pubDate", "date")
_TEXT_TAGS = ("encoded", "description", "content", "summary")


@dataclass(frozen=True)
class RawItem:
    source_id: str
    title: str
    link: str
    published_at: datetime
    text: str
    transcript_url: str = ""


class FeedError(RuntimeError):
    pass


def fetch_feed(source: dict, timeout: int = FETCH_TIMEOUT_S, http_get: Callable | None = None) -> list[RawItem]:
    """The feed's items, or [] when it cannot be fetched or read."""
    http_get = http_get or _default_get
    try:
        response = http_get(source["feed_url"], timeout=timeout)
        if response.status_code != 200:
            raise FeedError(f"HTTP {response.status_code}")
        return parse_feed(source, response.content)
    except Exception as exc:  # one broken feed must not stop the others
        log.warning("radar: feed %s could not be read: %s", source["id"], exc)
        return []


def parse_feed(source: dict, content: bytes) -> list[RawItem]:
    root = ET.fromstring(_as_parseable_xml(content))
    items = []
    for element in root.iter():
        if _local(element.tag) not in ("item", "entry"):
            continue
        item = _item(source, element)
        if item is not None:
            items.append(item)
    return items


def _default_get(url: str, **kwargs):
    return requests.get(url, headers={"User-Agent": USER_AGENT}, **kwargs)


def _as_parseable_xml(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace").lstrip("﻿")
    # A str with an encoding declaration is re-read by expat under that encoding; drop it.
    text = _XML_DECLARATION.sub("", text, count=1)
    text = _NAMED_ENTITY.sub(_numeric_entity, text)
    return _BARE_AMPERSAND.sub("&amp;", text)


def _numeric_entity(match: re.Match) -> str:
    name = match.group(1)
    if name in _XML_ENTITIES or name not in name2codepoint:
        return match.group(0)
    return f"&#{name2codepoint[name]};"


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _item(source: dict, element: ET.Element) -> RawItem | None:
    children = list(element)
    published_at = _published_at(children)
    if published_at is None:
        return None
    title = _plain_text(_first_text(children, ("title",)))
    return RawItem(
        source_id=source["id"],
        title=title,
        link=_link(children) or source["fallback_link"],
        published_at=published_at,
        text=_item_text(element, children),
        transcript_url=_transcript_url(children),
    )


def _first_text(children: list, names: tuple[str, ...]) -> str:
    for name in names:
        for child in children:
            if _local(child.tag) == name and (child.text or "").strip():
                return child.text.strip()
    return ""


def _published_at(children: list) -> datetime | None:
    for name in _DATE_TAGS:
        raw = _first_text(children, (name,))
        if raw:
            parsed = _parse_date(raw)
            if parsed is not None:
                return parsed
    return None


def _parse_date(raw: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _link(children: list) -> str:
    for child in children:
        if _local(child.tag) != "link":
            continue
        href = child.get("href")
        if href and child.get("rel", "alternate") == "alternate":
            return href.strip()
        if not href and (child.text or "").strip().startswith("http"):
            return child.text.strip()
    # A permalink guid (the Ads API anchors its notes this way) beats the show's home page.
    guid = _first_text(children, ("guid", "id"))
    return guid if guid.startswith("https://") else ""


def _item_text(element: ET.Element, children: list) -> str:
    raw = _first_text(children, _TEXT_TAGS)
    if not raw:
        # YouTube nests the video description in <media:group>.
        for node in element.iter():
            if _local(node.tag) == "description" and (node.text or "").strip():
                raw = node.text.strip()
                break
    return _plain_text(raw)


def _transcript_url(children: list) -> str:
    for child in children:
        if _local(child.tag) == "transcript" and child.get("url", "").startswith("http"):
            return child.get("url").strip()
    return ""


def _plain_text(raw: str) -> str:
    text = _SCRIPT_OR_STYLE.sub(" ", raw)
    text = _BLOCK_TAG.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text))
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n", "\n".join(line for line in lines if line)).strip()

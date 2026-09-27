"""The Radar run end to end with fake feeds, links and AI: validation after the AI and confidence are code's job."""
from datetime import datetime

import pytest

from core.radar import feeds, pipeline, run as radar_run, store
from core.radar.verify import TIMEZONE

NOW = datetime(2026, 9, 28, 8, 0, tzinfo=TIMEZONE)

OFFICIAL = {"id": "ads-api", "name": "Amazon Ads API release notes", "person": "Amazon", "kind": "official",
            "feed_url": "https://feeds.example.com/ads.xml", "fallback_link": "https://amazon.example.com/notes",
            "is_official": True}
EXPERT = {"id": "expert-blog", "name": "Expert (blog)", "person": "Jane Expert", "kind": "blog",
          "feed_url": "https://feeds.example.com/expert.xml", "fallback_link": "https://expert.example.com/",
          "is_official": False}
SOURCES = (OFFICIAL, EXPERT)


def _rss(*items: tuple[str, str, str]) -> bytes:
    body = "".join(f"<item><title>{title}</title><link>{link}</link><pubDate>{date}</pubDate>"
                   f"<description>Text of {title}</description></item>" for title, link, date in items)
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{body}</channel></rss>".encode()


FEEDS = {
    OFFICIAL["feed_url"]: _rss(("Ads change", "https://amazon.example.com/change", "Sat, 26 Sep 2026 00:00:00 +0000")),
    EXPERT["feed_url"]: _rss(
        ("Expert on the ads change", "https://expert.example.com/1", "Sun, 27 Sep 2026 12:00:00 +0000"),
        ("Expert tip", "https://expert.example.com/2", "Fri, 25 Sep 2026 12:00:00 +0000"),
        ("Old post", "https://expert.example.com/old", "Tue, 01 Sep 2026 12:00:00 +0000"),
        ("Dead post", "https://expert.example.com/dead", "Sun, 27 Sep 2026 13:00:00 +0000"),
    ),
}


class _Response:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content


def _http_get(url, **kwargs):
    if url in FEEDS:
        return _Response(200, FEEDS[url])
    return _Response(404 if url.endswith("/dead") else 200)


def _answer(*topics):
    return {"structured_output": {"topics": list(topics)}, "usage": {"input_tokens": 10}}


def _topic(ids, rank, title="T"):
    return {"item_ids": ids, "title_es": title, "summary_es": "Resumen.", "implications_es": "Implica.", "rank": rank}


def _run(answer, save=None):
    calls = []

    def ai_ask(**call):
        calls.append(call)
        return answer

    result = pipeline.run(NOW, http_get=_http_get, ai_ask=ai_ask, save=save, sources=SOURCES)
    return result, calls


def test_only_items_in_window_with_a_live_link_reach_the_ai():
    result, calls = _run(_answer())
    assert [entry.item.title for entry in result.items] == ["Expert on the ads change", "Ads change", "Expert tip"]
    report = {entry.source_id: entry for entry in result.report}
    assert (report["expert-blog"].fetched, report["expert-blog"].in_window, report["expert-blog"].link_ok) == (4, 3, 2)
    sent = calls[0]["context"][1]["content"]
    assert '"id": "R01"' in sent and '"id": "R03"' in sent and '"id": "R04"' not in sent
    assert "Dead post" not in sent and "Old post" not in sent


def test_confidence_is_computed_and_a_topic_citing_an_unknown_id_is_dropped():
    saved = []
    result, _ = _run(_answer(
        _topic(["R01", "R02"], 2, "Mixed"),     # expert + official
        _topic(["R02"], 1, "Official only"),
        _topic(["R03"], 3, "Expert only"),
        _topic(["R03", "R99"], 4, "Invented"),  # R99 was never sent
    ), save=saved.extend)

    assert [row["title_es"] for row in result.rows] == ["Official only", "Mixed", "Expert only"]
    assert [row["confidence"] for row in result.rows] == ["official", "confirmed", "expert"]
    assert [row["rank"] for row in result.rows] == [1, 2, 3]
    assert result.dropped_topics == 1
    assert saved == result.rows


def test_saved_rows_are_well_formed():
    result, _ = _run(_answer(_topic(["R01", "R02"], 1, "Mixed")))
    [mixed] = result.rows
    assert set(mixed) == {"week_start", "title_es", "summary_es", "implications_es", "confidence", "sources",
                          "primary_link", "primary_published_at", "rank", "input_digest", "agent_version", "model",
                          "usage", "created_at"}
    assert mixed["week_start"] == "2026-09-28"
    # Amazon's own item is the primary link even when an expert's item is newer.
    assert mixed["primary_link"] == "https://amazon.example.com/change"
    source = mixed["sources"][0]
    assert set(source) == {"source_id", "name", "person", "title", "link", "published_at", "verified_at",
                           "http_status", "is_official"}
    assert source["http_status"] == 200 and source["link"] == "https://expert.example.com/1"
    assert mixed["model"] and mixed["input_digest"] and mixed["usage"] == {"input_tokens": 10}


def test_a_topic_whose_only_link_is_taken_is_dropped():
    result, _ = _run(_answer(_topic(["R02"], 1, "First"), _topic(["R02"], 2, "Same item again")))
    assert [row["title_es"] for row in result.rows] == ["First"]
    assert result.dropped_topics == 1


def test_an_answer_without_the_schema_fails_loudly():
    with pytest.raises(pipeline.RadarError):
        _run({"text": "sin formato"})


def test_official_items_skip_the_cap_and_experts_get_the_room_left():
    from core.radar.verify import MAX_ITEMS_PER_RUN

    expert_items = [(f"Expert {n}", f"https://expert.example.com/p{n}", f"Sun, 27 Sep 2026 {n % 24:02d}:00:00 +0000")
                    for n in range(MAX_ITEMS_PER_RUN + 5)]
    feeds_by_url = {
        # Older than every expert item: a plain newest-first cap would leave it out.
        OFFICIAL["feed_url"]: _rss(("Ads change", "https://amazon.example.com/change",
                                    "Tue, 22 Sep 2026 00:00:00 +0000")),
        EXPERT["feed_url"]: _rss(*expert_items),
    }

    def http_get(url, **kwargs):
        return _Response(200, feeds_by_url[url]) if url in feeds_by_url else _Response(200)

    result = pipeline.run(NOW, http_get=http_get, sources=SOURCES)
    titles = [entry.item.title for entry in result.items]
    assert "Ads change" in titles
    assert len(result.items) == MAX_ITEMS_PER_RUN
    assert sum(entry.source["is_official"] for entry in result.items) == 1
    assert {entry.source_id: entry.sent for entry in result.report} == {"ads-api": 1, "expert-blog": MAX_ITEMS_PER_RUN - 1}


def test_dry_run_calls_neither_ai_nor_database():
    result = pipeline.run(NOW, http_get=_http_get, sources=SOURCES)
    assert len(result.items) == 3 and result.rows == []


def test_cli_dry_run_touches_neither_ai_nor_database(monkeypatch, capsys):
    def _forbidden(*args, **kwargs):
        raise AssertionError("a dry run must not reach this")

    monkeypatch.setattr(feeds, "_default_get", lambda url, **kwargs: _Response(404))
    monkeypatch.setattr("ai.client.ask", _forbidden)
    monkeypatch.setattr(store, "save_rows", _forbidden)
    monkeypatch.setattr(radar_run, "_worker_rest", _forbidden)

    assert radar_run.main(["--dry-run"]) == 0
    assert "TOTAL" in capsys.readouterr().out


def test_cli_full_run_refuses_without_database(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv(radar_run.JWT_ENV, raising=False)
    assert radar_run.main([]) == radar_run.CONFIG_ERROR_EXIT

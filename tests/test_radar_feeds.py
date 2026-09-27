"""Radar feed parsing: RSS and Atom, tolerant decoding, dateless items dropped, fallback links. No network."""
from datetime import datetime, timezone
from pathlib import Path

from core.radar.feeds import fetch_feed, parse_feed

FIXTURES = Path(__file__).parent / "fixtures" / "radar"
SOURCE = {"id": "test-source", "feed_url": "https://example.com/feed", "fallback_link": "https://example.com/show"}


def _parse(name: str):
    return parse_feed(SOURCE, (FIXTURES / name).read_bytes())


class _Response:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content


def test_rss_blog_item_fields_and_html_stripped():
    items = _parse("rss_blog.xml")
    assert len(items) == 2
    first = items[0]
    assert first.title == "Prime Big Deal Days 2026 PPC Playbook: Bids & Budgets"
    assert first.link == "https://www.adbadger.com/blog/prime-big-deal-days-ppc-strategy/"
    assert first.published_at == datetime(2026, 9, 25, 17, 7, 32, tzinfo=timezone.utc)
    # content:encoded wins over description; tags and scripts are gone.
    assert first.text == "Raise budgets before the event.\nLower bids after it."
    assert items[1].text == "Plain description & more."


def test_youtube_atom_uses_published_and_media_description():
    items = _parse("youtube_atom.xml")
    # The entry with only <updated> has no publication date: it never enters.
    assert len(items) == 1
    video = items[0]
    assert video.link == "https://www.youtube.com/watch?v=3RN-BEM9BCA"
    assert video.published_at == datetime(2026, 9, 25, 17, 2, 16, tzinfo=timezone.utc)
    assert video.text == "Steven walks through order automation for Amazon sellers."


def test_utf8_body_behind_a_us_ascii_declaration():
    items = _parse("ads_api_bad_encoding.xml")
    assert len(items) == 1
    assert "dashboard—no download" in items[0].text
    # No <link>: the permalink guid is the item's own page.
    assert items[0].link == "https://advertising.amazon.com/API/docs/en-us/release-notes/index#bulk-operations-preview"


def test_dateless_items_are_dropped_and_linkless_items_use_the_fallback():
    items = _parse("podcast_edge_cases.xml")
    assert [item.title for item in items] == ["Episode without a link"]
    episode = items[0]
    assert episode.link == SOURCE["fallback_link"]
    assert episode.transcript_url == "https://hosting-media.example.com/transcript.srt"
    assert "Sponsored Brands & video — with a transcript." in episode.text
    assert episode.published_at.tzinfo is not None


def test_fetch_feed_never_raises():
    assert fetch_feed(SOURCE, http_get=lambda url, **kw: _Response(503)) == []
    assert fetch_feed(SOURCE, http_get=lambda url, **kw: _Response(200, b"<html>not a feed")) == []

    def _boom(url, **kw):
        raise ConnectionError("down")

    assert fetch_feed(SOURCE, http_get=_boom) == []


def test_fetch_feed_parses_a_good_response():
    body = (FIXTURES / "rss_blog.xml").read_bytes()
    assert len(fetch_feed(SOURCE, http_get=lambda url, **kw: _Response(200, body))) == 2

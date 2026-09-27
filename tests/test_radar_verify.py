"""Radar verification rules: 7-day window in Argentina time, link checks through oEmbed, caps. No network."""
from datetime import date, datetime, timedelta, timezone

import pytest

from core.radar.feeds import RawItem
from core.radar.verify import (
    MAX_ITEMS_PER_RUN,
    MAX_TEXT_CHARS,
    TIMEZONE,
    cap_items,
    check_link,
    truncate_text,
    week_start,
    with_truncated_text,
    within_window,
)

NOW = datetime(2026, 9, 28, 8, 0, tzinfo=TIMEZONE)  # Monday 8:00 in Argentina


def _item(published_at: datetime, text: str = "t", title: str = "x") -> RawItem:
    return RawItem("s", title, "https://example.com/a", published_at, text)


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


@pytest.mark.parametrize("delta, inside", [
    (timedelta(0), True),
    (timedelta(days=7), True),
    (timedelta(days=7, seconds=1), False),
    (timedelta(seconds=-1), False),  # dated in the future
])
def test_window_edges(delta, inside):
    assert within_window(_item(NOW - delta), NOW) is inside


def test_window_compares_instants_whatever_the_feed_timezone():
    # 2026-09-21 10:59 UTC is 07:59 in Argentina: seven days and one minute before NOW.
    assert not within_window(_item(datetime(2026, 9, 21, 10, 59, tzinfo=timezone.utc)), NOW)
    assert within_window(_item(datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc)), NOW)


def test_week_start_is_the_argentine_monday():
    assert week_start(NOW) == date(2026, 9, 28)
    # Monday 01:00 UTC is still Sunday in Argentina.
    assert week_start(datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)) == date(2026, 9, 21)


def test_youtube_is_checked_through_oembed():
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params))
        return _Response(404 if params and "DELETED" in params["url"] else 200)

    assert check_link("https://www.youtube.com/watch?v=3RN-BEM9BCA", fake_get) == (True, 200)
    assert check_link("https://www.youtube.com/watch?v=DELETED0000", fake_get) == (False, 404)
    assert all(url == "https://www.youtube.com/oembed" for url, _ in calls)
    assert calls[0][1] == {"url": "https://www.youtube.com/watch?v=3RN-BEM9BCA", "format": "json"}


def test_other_links_need_a_200():
    assert check_link("https://www.adbadger.com/blog/x/", lambda url, **kw: _Response(200)) == (True, 200)
    assert check_link("https://www.adbadger.com/blog/gone/", lambda url, **kw: _Response(404)) == (False, 404)

    def _boom(url, **kw):
        raise TimeoutError

    assert check_link("https://slow.example.com/", _boom) == (False, None)


def test_cap_keeps_the_newest():
    items = [_item(NOW - timedelta(hours=hours), title=str(hours)) for hours in range(MAX_ITEMS_PER_RUN + 5)]
    capped = cap_items(reversed(items))
    assert len(capped) == MAX_ITEMS_PER_RUN
    assert capped[0].title == "0" and capped[-1].title == str(MAX_ITEMS_PER_RUN - 1)


def test_truncation():
    long_text = "a" * (MAX_TEXT_CHARS + 10)
    assert len(truncate_text(long_text)) == MAX_TEXT_CHARS + 1 and truncate_text(long_text).endswith("…")
    assert truncate_text("short") == "short"
    assert with_truncated_text(_item(NOW, long_text)).text == truncate_text(long_text)

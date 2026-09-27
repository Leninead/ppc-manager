"""Radar's verification rules: pure logic, with the HTTP call injected.

An item enters the digest only if its own feed dates it within the window and its original link answers.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from core.radar.feeds import RawItem

TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
WINDOW_DAYS = 7
MAX_TEXT_CHARS = 1500
MAX_ITEMS_PER_RUN = 40
LINK_TIMEOUT_S = 20
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
_OEMBED_URL = "https://www.youtube.com/oembed"


def within_window(item: RawItem, now: datetime, days: int = WINDOW_DAYS) -> bool:
    """Published in the `days` before `now`, Argentina time; a date in the future does not count."""
    local_now = now.astimezone(TIMEZONE)
    published = item.published_at.astimezone(TIMEZONE)
    return local_now - timedelta(days=days) <= published <= local_now


def week_start(now: datetime) -> date:
    """The ISO Monday of `now`'s week, Argentina time."""
    local_day = now.astimezone(TIMEZONE).date()
    return local_day - timedelta(days=local_day.weekday())


def check_link(url: str, http_get: Callable) -> tuple[bool, int | None]:
    """(answers, HTTP status). YouTube answers 200 for any watch URL, even a deleted video; oEmbed does not."""
    try:
        if _is_youtube(url):
            response = http_get(_OEMBED_URL, params={"url": url, "format": "json"}, timeout=LINK_TIMEOUT_S)
        else:
            response = http_get(url, timeout=LINK_TIMEOUT_S)
    except Exception:
        return False, None
    status = getattr(response, "status_code", None)
    return status == 200, status


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def cap_items(items: Iterable, limit: int = MAX_ITEMS_PER_RUN) -> list:
    """The `limit` newest items: anything with a `published_at`."""
    return sorted(items, key=lambda item: item.published_at, reverse=True)[:limit]


def with_truncated_text(item: RawItem) -> RawItem:
    return replace(item, text=truncate_text(item.text))


def _is_youtube(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in _YOUTUBE_HOSTS

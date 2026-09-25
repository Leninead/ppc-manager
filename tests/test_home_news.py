"""The home news catalog: every item is valid and every page it opens exists in the menu."""
from __future__ import annotations

from datetime import date

from core.home_news import KINDS, NEWS, count_since, latest, validate_news
from core.navigation import all_pages


def _item(item_id: str, day: date, page=None, kind: str = "new") -> dict:
    return {"id": item_id, "title": item_id, "description": "desc", "date": day, "kind": kind, "page": page}


def test_catalog_is_valid():
    assert validate_news(NEWS, all_pages()) == []


def test_every_page_exists_in_the_menu():
    pages = set(all_pages())
    for item in NEWS:
        assert item["page"] is None or item["page"] in pages, item["id"]
        assert item["kind"] in KINDS


def test_latest_orders_by_date_and_keeps_catalog_order_on_ties():
    news = (
        _item("old", date(2026, 9, 1)),
        _item("tie-first", date(2026, 9, 20)),
        _item("newest", date(2026, 9, 22)),
        _item("tie-second", date(2026, 9, 20)),
    )
    assert [item["id"] for item in latest(news, 3)] == ["newest", "tie-first", "tie-second"]
    assert [item["id"] for item in latest(news, 10)][-1] == "old"


def test_count_since_uses_a_seven_day_window_exclusive_of_its_start():
    today = date(2026, 9, 24)
    news = (
        _item("today", today),
        _item("six-days", date(2026, 9, 18)),
        _item("seven-days", date(2026, 9, 17)),
        _item("eight-days", date(2026, 9, 16)),
    )
    assert count_since(news, today) == 2
    assert count_since(news, today, days=8) == 3


def test_validate_flags_unknown_page_and_duplicate_id():
    news = (
        _item("same", date(2026, 9, 1), page="🏠 No existe"),
        _item("same", date(2026, 9, 2)),
    )
    errors = validate_news(news, all_pages())
    assert any("no existe en el menú" in error for error in errors)
    assert any("id duplicado" in error for error in errors)


def test_validate_flags_bad_kind_missing_fields_and_blank_text():
    news = (
        _item("bad-kind", date(2026, 9, 1), kind="fix"),
        {"id": "no-page", "title": "  ", "description": "d", "date": date(2026, 9, 1), "kind": "new"},
        {"id": "no-date", "title": "t", "description": "d", "kind": "new", "page": None},
    )
    errors = validate_news(news, all_pages())
    assert any("bad-kind" in error and "kind" in error for error in errors)
    assert any("no-page" in error and "page" in error for error in errors)
    assert any("no-page" in error and "title vacío" in error for error in errors)
    assert any("no-date" in error and "date" in error for error in errors)

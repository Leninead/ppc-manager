"""compare: each row next to the same row in the period before, with the change already worked out."""
from __future__ import annotations

from datetime import date

import pytest

from core.amazon_ads.report_provider import ProfileOption
from services.mcp_server.tools.period_comparison import (
    ComparisonWindow,
    activity_status,
    change_fields,
    change_leaders,
    compared_rows,
    compared_totals,
    comparison_window,
)

PROFILE = ProfileOption.from_row({"profile_id": "1", "data_from": "2026-08-01", "data_through": "2026-09-16",
                                  "currency_code": "USD"})


def test_the_previous_period_is_the_one_of_the_same_length_right_before():
    assert comparison_window(PROFILE, date(2026, 9, 10), date(2026, 9, 16), "previous") == ComparisonWindow(
        date(2026, 9, 3), date(2026, 9, 9))


def test_exact_dates_compare_against_the_days_asked_for():
    """An unfinished month goes against the same days of the one before."""
    window = comparison_window(PROFILE, date(2026, 9, 1), date(2026, 9, 12), "", "2026-08-01", "2026-08-12")

    assert (window.start, window.end) == (date(2026, 8, 1), date(2026, 8, 12))


def test_a_previous_period_the_account_only_partly_has_is_clipped_and_one_it_lacks_is_said():
    clipped = comparison_window(PROFILE, date(2026, 8, 10), date(2026, 8, 30), "previous")
    outside = comparison_window(PROFILE, date(2026, 8, 1), date(2026, 8, 10), "previous")

    assert (clipped.start, clipped.end) == (date(2026, 8, 1), date(2026, 8, 9)) and "recortó" in clipped.note
    assert isinstance(outside, str) and "No hay con qué comparar" in outside
    assert comparison_window(PROFILE, date(2026, 9, 10), date(2026, 9, 16), "") is None
    with pytest.raises(ValueError, match="compare"):
        comparison_window(PROFILE, date(2026, 9, 10), date(2026, 9, 16), "last_year")


def test_a_row_takes_seven_change_fields_and_no_percent_over_nothing():
    current = {"group": "a", "spend": 30.0, "sales": 120.0, "orders": 4, "acos": 25.0}

    moved = change_fields(current, {"spend": 20.0, "sales": 100.0, "orders": 5, "acos": 20.0}, "spend")
    new = change_fields(current, None, "spend")

    assert moved == {"delta_spend_pct": 50.0, "delta_sales_pct": 20.0, "delta_orders_pct": -20.0,
                     "delta_acos_pp": 5.0, "previous_spend": 20.0, "previous_sales": 100.0, "delta_spend": 10.0}
    assert new["delta_spend_pct"] is None and new["delta_spend"] == 30.0 and new["previous_spend"] == 0.0


def test_a_row_that_only_ran_before_comes_back_with_zero_figures_and_status_gone():
    rows = [{"group": "a", "spend": 30.0, "sales": 0.0, "orders": 0, "acos": None}]
    before = [{"group": "a", "spend": 10.0, "sales": 0.0, "orders": 0, "acos": None},
              {"group": "b", "spend": 8.0, "sales": 16.0, "orders": 1, "acos": 50.0}]

    compared = compared_rows(rows, before, lambda row: row["group"], "spend",
                             lambda previous: {"group": previous["group"], "spend": 0.0, "sales": 0.0, "orders": 0,
                                               "acos": None})

    assert [(row["group"], row.get("status"), row["delta_spend"]) for row in compared] == [
        ("a", None, 20.0), ("b", "gone", -8.0)]
    assert compared[1]["delta_spend_pct"] == -100.0


def test_the_leaders_are_the_biggest_rise_and_the_biggest_fall_of_the_ordering_figure():
    rows = [{"campaign": "a", "delta_spend": 20.0}, {"campaign": "b", "delta_spend": -8.0},
            {"campaign": "c", "delta_spend": 2.0}, {"campaign": "d", "delta_spend": None}]

    assert change_leaders(rows, "spend", name="campaign") == {
        "biggest_rise": {"campaign": "a", "delta_spend": 20.0},
        "biggest_fall": {"campaign": "b", "delta_spend": -8.0}}


def test_the_whole_carries_its_own_change_and_the_previous_whole():
    totals = compared_totals({"spend": 30.0, "sales": 60.0, "orders": 3, "acos": 50.0},
                             {"spend": 20.0, "sales": 80.0, "orders": 4, "acos": 25.0})

    assert (totals["delta_spend_pct"], totals["delta_sales_pct"], totals["delta_acos_pp"]) == (50.0, -25.0, 25.0)
    assert totals["previous"]["spend"] == 20.0


def test_a_listed_row_is_new_or_gone_by_whether_it_spent_in_each_period():
    assert activity_status({"spend": 5.0}, {"spend": 0.0}) == {"status": "new"}
    assert activity_status({"spend": 0.0}, {"spend": 3.0}) == {"status": "gone"}
    assert activity_status({"spend": 5.0}, {"spend": 3.0}) == {}

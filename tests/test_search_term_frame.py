"""Tests for core/search_term/frame.py: canonical columns M2 detects and ratios from totals."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from core.search_term import frame as canonical
from core.search_term.frame import (
    HIDDEN_ID_COLUMNS,
    SOURCE_API,
    SOURCE_FILE,
    SearchTermSource,
    add_ratios,
    console_columns,
)
from modules.pages.search_term_report import _detect_cols

M2_FORBIDDEN_FRAGMENTS = ("portfolio", "campaign name", "ad group", "sales", "order", "click", "impression",
                          "spend", "acos", "ctr", "conversion", "match type")


def _expected_detection(days: int) -> dict[str, str]:
    return {
        "search_term": "Customer Search Term",
        "spend": "Spend",
        "sales": f"{days} Day Total Sales",
        "orders": f"{days} Day Total Orders (#)",
        "clicks": "Clicks",
        "impressions": "Impressions",
        "acos": "Total Advertising Cost of Sales (ACoS)",
        "ctr": "Click-Thru Rate (CTR)",
        "cvr": f"{days} Day Conversion Rate",
        "campaign": "Campaign Name",
        "ad_group": "Ad Group Name",
        "match_type": "Match Type",
        "portfolio": "Portfolio name",
    }


def _totals_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "Impressions": [1600, 0, 500],
        "Clicks": [40, 0, 3],
        "Spend": [30.0, 0.0, 4.2],
        "7 Day Total Sales": [120.0, 0.0, 0.0],
        "7 Day Total Orders (#)": [3, 0, 0],
    })


def test_console_columns_exact_order_for_seven_days():
    assert console_columns(7) == [
        "Customer Search Term", "Campaign Name", "Ad Group Name", "Portfolio name", "Match Type", "Targeting",
        "Impressions", "Clicks", "Spend", "7 Day Total Sales", "7 Day Total Orders (#)", "7 Day Total Units (#)",
        "Click-Thru Rate (CTR)", "Cost Per Click (CPC)", "7 Day Conversion Rate",
        "Total Advertising Cost of Sales (ACoS)",
    ]


def test_console_columns_follow_attribution_days():
    columns = console_columns(14)
    assert "14 Day Total Sales" in columns
    assert "14 Day Total Units (#)" in columns
    assert not any(column.startswith("7 Day") for column in columns)


def test_sales_column_precedes_acos_column():
    columns = console_columns(7)
    assert columns.index("7 Day Total Sales") < columns.index(canonical.ACOS)


@pytest.mark.parametrize("days", [7, 14])
def test_m2_detects_every_canonical_column_with_hidden_ids_present(days):
    frame = pd.DataFrame(columns=console_columns(days) + list(HIDDEN_ID_COLUMNS))
    assert _detect_cols(frame) == _expected_detection(days)


def test_hidden_columns_are_underscored_and_invisible_to_m2_detection():
    for column in HIDDEN_ID_COLUMNS:
        assert column.startswith("_")
        assert not any(fragment in column.lower() for fragment in M2_FORBIDDEN_FRAGMENTS), column


def test_hidden_columns_carry_the_bulk_guard_flags():
    assert canonical.ANY_WINDOW_PURCHASES in HIDDEN_ID_COLUMNS
    assert canonical.PORTFOLIO_NAME_MISSING in HIDDEN_ID_COLUMNS


@pytest.mark.parametrize("value, expected", [
    ("MXN", "MXN"), (" usd ", "USD"), ("", ""), (None, ""), (float("nan"), ""), ("US$", ""), ("EURO", ""),
    ("<b>", ""), ("M X", ""), ("ÉUR", ""),
])
def test_valid_currency_code_keeps_only_three_ascii_letters(value, expected):
    assert canonical.valid_currency_code(value) == expected


def test_add_ratios_computes_percentages_from_totals():
    with_ratios = add_ratios(_totals_frame(), 7)
    first = with_ratios.iloc[0]
    assert first[canonical.CTR] == 2.5
    assert first[canonical.CPC] == 0.75
    assert first["7 Day Conversion Rate"] == 7.5
    assert first[canonical.ACOS] == 25.0


def test_add_ratios_is_zero_when_denominator_is_zero():
    with_ratios = add_ratios(_totals_frame(), 7)
    no_traffic = with_ratios.iloc[1]
    assert (no_traffic[canonical.CTR], no_traffic[canonical.CPC], no_traffic["7 Day Conversion Rate"],
            no_traffic[canonical.ACOS]) == (0.0, 0.0, 0.0, 0.0)
    assert with_ratios.iloc[2][canonical.ACOS] == 0.0
    assert with_ratios[[canonical.CTR, canonical.CPC, canonical.ACOS]].notna().all().all()


def test_add_ratios_rounds_to_two_decimals():
    frame = pd.DataFrame({"Impressions": [3], "Clicks": [3], "Spend": [10.0],
                          "7 Day Total Sales": [30.0], "7 Day Total Orders (#)": [1]})
    with_ratios = add_ratios(frame, 7)
    assert with_ratios.iloc[0][canonical.CPC] == 3.33
    assert with_ratios.iloc[0]["7 Day Conversion Rate"] == 33.33
    assert with_ratios.iloc[0][canonical.ACOS] == 33.33


def test_add_ratios_overwrites_stale_ratio_columns():
    frame = _totals_frame()
    frame[canonical.ACOS] = 999.0
    assert add_ratios(frame, 7).iloc[0][canonical.ACOS] == 25.0


def test_add_ratios_accepts_numeric_text():
    frame = _totals_frame().astype(str)
    assert add_ratios(frame, 7).iloc[0][canonical.ACOS] == 25.0


def test_add_ratios_does_not_mutate_the_input():
    frame = _totals_frame()
    before = frame.copy()
    add_ratios(frame, 7)
    pd.testing.assert_frame_equal(frame, before)


def test_add_ratios_puts_console_columns_first_and_hidden_columns_last():
    frame = _totals_frame()
    frame.insert(0, "_campaign_id", ["1", "2", "3"])
    frame.insert(1, "Extra", ["a", "b", "c"])
    frame["Customer Search Term"] = ["x", "y", "z"]
    columns = list(add_ratios(frame, 7).columns)
    assert columns[0] == "Customer Search Term"
    assert columns[-1] == "_campaign_id"
    assert columns.index("7 Day Total Sales") < columns.index(canonical.ACOS) < columns.index("Extra")


def test_add_ratios_rejects_frame_without_totals():
    with pytest.raises(ValueError, match="7 Day Total Sales"):
        add_ratios(_totals_frame().drop(columns=["7 Day Total Sales"]), 7)


def test_add_ratios_uses_the_attribution_window_columns():
    frame = _totals_frame().rename(columns={"7 Day Total Sales": "14 Day Total Sales",
                                            "7 Day Total Orders (#)": "14 Day Total Orders (#)"})
    with_ratios = add_ratios(frame, 14)
    assert with_ratios.iloc[0]["14 Day Conversion Rate"] == 7.5
    assert with_ratios.iloc[0][canonical.ACOS] == 25.0


def _source(frame: pd.DataFrame) -> SearchTermSource:
    return SearchTermSource(frame=frame, source=SOURCE_API, currency_code="MXN", label="Marca Demo · MX",
                            signature="abc123", attribution_days=7, bulk_ready=True)


def test_search_term_source_defaults_and_immutability():
    source = _source(pd.DataFrame())
    assert source.profile_id == ""
    assert SOURCE_FILE != SOURCE_API
    with pytest.raises(dataclasses.FrozenInstanceError):
        source.label = "otro"


def test_search_term_sources_compare_by_identity_without_touching_frames():
    frame = pd.DataFrame({"Spend": [1.0]})
    assert _source(frame) != _source(frame)

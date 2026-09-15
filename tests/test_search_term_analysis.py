"""What the STR agent analyzes (core/search_term_analysis.py): parameters, the canonical window and the payload."""
from datetime import date

import pandas as pd
import pytest

from ai.agent_call import build_agent_call
from core.search_term_analysis import (
    BLOCKED_NO_CANDIDATES,
    StrAnalysisParams,
    add_metric_columns,
    build_analysis_input,
    canonical_analysis_window,
    detect_columns,
    harvest_candidate_rows,
    normalized_brand_terms,
    suggested_bid,
)
from core.search_term_frame import add_ratios
from modules.pages.search_term_source import default_period_key, period_options

_ROWS = [
    {"Customer Search Term": "cheap toy box", "Campaign Name": "LK - Broad", "Ad Group Name": "AG", "Impressions": 900,
     "Clicks": 40, "Spend": 25.0, "7 Day Total Sales": 0.0, "7 Day Total Orders (#)": 0},
    {"Customer Search Term": "luna pajamas", "Campaign Name": "LK - Exact", "Ad Group Name": "AG", "Impressions": 800,
     "Clicks": 30, "Spend": 10.0, "7 Day Total Sales": 150.0, "7 Day Total Orders (#)": 6},
    {"Customer Search Term": "sleep sack", "Campaign Name": "LK - Broad", "Ad Group Name": "AG", "Impressions": 100,
     "Clicks": 2, "Spend": 1.0, "7 Day Total Sales": 0.0, "7 Day Total Orders (#)": 0},
]


def _frame(rows=_ROWS):
    frame = add_ratios(pd.DataFrame(rows), 7)
    cols = detect_columns(frame)
    add_metric_columns(frame, cols)
    return frame, cols


def _input(params=None, rows=_ROWS, **options):
    frame, cols = _frame(rows)
    return build_analysis_input(frame, cols, params or StrAnalysisParams.defaults("USD"), currency_code="USD",
                                lang="es", **options)


def test_dollar_accounts_start_with_a_price_and_other_currencies_start_without_one():
    assert StrAnalysisParams.defaults("USD").price == 30.0
    assert StrAnalysisParams.defaults("MXN").price is None
    assert StrAnalysisParams.defaults("MXN").harvest_price is None


def test_brand_terms_in_another_order_or_case_are_the_same_parameters():
    first = StrAnalysisParams.from_dict({"brand_terms": ["Luna", "acme", "luna "]}, "USD")
    second = StrAnalysisParams.from_dict({"brand_terms": "acme, LUNA"}, "USD")

    assert first == second
    assert first.digest == second.digest
    assert normalized_brand_terms("b, a, ,a") == ("a", "b")


def test_saved_parameters_round_trip_and_fill_missing_keys_with_the_currency_defaults():
    params = StrAnalysisParams(45, 25.0, 35, 26.0, 20, ("acme",))

    assert StrAnalysisParams.from_dict(params.as_dict(), "MXN") == params
    assert StrAnalysisParams.from_dict({"target_acos": 40}, "MXN") == StrAnalysisParams(40, None, 30, None, 15, ())


@pytest.mark.parametrize("data_from, data_through, expected", [
    (date(2026, 7, 11), date(2026, 9, 14), (date(2026, 8, 16), date(2026, 9, 14))),
    (date(2026, 9, 1), date(2026, 9, 14), (date(2026, 9, 1), date(2026, 9, 14))),
    (None, date(2026, 9, 14), (date(2026, 8, 16), date(2026, 9, 14))),
])
def test_the_canonical_window_is_the_period_m2_opens_on(data_from, data_through, expected):
    options = period_options(data_from, data_through)
    default_option = next(option for option in options if option.key == default_period_key(options))

    assert canonical_analysis_window(data_from, data_through) == expected == (default_option.start,
                                                                                default_option.end)


def test_the_payload_carries_no_date_and_no_tab_one_slider():
    built = _input()

    assert built.blocked_reason == ""
    assert "Fecha" not in built.data.kpis and "Target ACoS" not in built.data.kpis
    assert built.data.kpis["Total Spend"] == "$36.00"


def test_the_same_data_and_parameters_give_the_same_input_digest():
    first, second = build_agent_call("str", _input().data), build_agent_call("str", _input().data)
    other_params = build_agent_call("str", _input(StrAnalysisParams(45, 30.0, 30, 30.0, 15, ())).data)
    other_data = build_agent_call("str", _input(rows=_ROWS[:2]).data)

    assert first.input_digest == second.input_digest
    assert first.agent_version == second.agent_version
    assert other_params.input_digest != first.input_digest
    assert other_data.input_digest != first.input_digest


def test_without_prices_the_payload_is_built_without_rule_three_or_suggested_bids():
    # 1 click and 5.00 spent without an order: only Rule 3 (spend >= price x 0.5) makes it a negative.
    rows = _ROWS + [{"Customer Search Term": "baby gate", "Campaign Name": "LK - Broad", "Ad Group Name": "AG",
                     "Impressions": 300, "Clicks": 1, "Spend": 5.0, "7 Day Total Sales": 0.0,
                     "7 Day Total Orders (#)": 0}]
    priced = _input(StrAnalysisParams(30, 10.0, 30, 10.0, 15, ()), rows=rows)
    no_prices = _input(StrAnalysisParams(30, None, 30, None, 15, ()), rows=rows)

    assert "baby gate" in [row["Search Term"] for row in priced.negative_records]
    assert no_prices.blocked_reason == ""
    assert "baby gate" not in [row["Search Term"] for row in no_prices.negative_records]
    assert (no_prices.data.precio, no_prices.data.harvest_precio, no_prices.spend_threshold) == (
        None, None, float("inf"))
    assert [row["Bid Sugerido"] for row in no_prices.harvest_records] == [None]
    assert [row["Bid Sugerido"] for row in priced.harvest_records] != [None]


@pytest.mark.parametrize("cvr_percent, price, target_acos, expected", [
    (10.0, 30.0, 30, 0.9),      # the formula, below the ceiling
    (700.0, 30.0, 30, 9.0),     # CVR capped at 100%: never above price x target ACoS
    (150.0, 41.07, 30, 12.32),  # the ceiling is rounded down to the cent
    (150.0, 29.99, 30, 8.99),   # 8.997 would round up past the ceiling
    (100.0, 16.4, 30, 4.92),    # 16.4 x 30 is 491.99999999999994 in floats, still 4.92
    (100.0, 8.20, 30, 2.46),
    (0.5, 30.0, 30, 0.10),      # Amazon's minimum bid
    (100.0, 0.25, 30, 0.07),    # a ceiling under the minimum wins: that bid cannot be profitable
])
def test_the_suggested_bid_follows_the_inv1_ceiling(cvr_percent, price, target_acos, expected):
    assert suggested_bid(cvr_percent, price, target_acos) == expected


def test_harvest_rows_that_convert_more_than_they_click_get_the_ceiling_bid():
    # 7-day attribution can credit more orders than clicks: CVR 400%.
    frame, cols = _frame([{"Customer Search Term": "luna pajamas", "Campaign Name": "LK - Broad", "Ad Group Name": "AG",
                           "Impressions": 80, "Clicks": 2, "Spend": 2.0, "7 Day Total Sales": 120.0,
                           "7 Day Total Orders (#)": 8}])

    harvest = harvest_candidate_rows(frame, cols, min_clicks=1, price=29.99, target_acos=30)

    assert (harvest["CVR%"].tolist(), harvest["Bid Sugerido"].tolist()) == ([400.0], [8.99])


def test_no_negative_or_harvest_candidates_blocks_the_payload():
    quiet = [dict(_ROWS[2], Clicks=1, Spend=0.1)]

    assert _input(rows=quiet).blocked_reason == BLOCKED_NO_CANDIDATES


def test_harvest_without_a_price_has_no_suggested_bid_and_only_file_sources_mark_existing_exact():
    frame, cols = _frame()
    params = StrAnalysisParams(30, 30.0, 30, 30.0, 15, ())

    from_api = build_analysis_input(frame, cols, params, currency_code="USD", lang="es")
    from_file = build_analysis_input(frame, cols, params, currency_code="USD", lang="es",
                                     existing_exact_terms={"luna pajamas"})

    assert [row["Search Term"] for row in from_api.harvest_records] == ["luna pajamas"]
    assert "Ya en Exact" not in from_api.harvest_records[0]
    assert from_file.harvest_records[0]["Ya en Exact"] == "Ya en Exact activo"


def test_negatives_sent_to_the_ai_are_the_high_and_medium_priority_ones():
    built = _input()

    assert [(row["Search Term"], row["Prioridad"]) for row in built.negative_records] == [("cheap toy box", "Alta")]

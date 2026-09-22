"""Análisis de Funnel rules (core/funnel/coverage.py): the cross of search terms with campaigns, and harvest."""
import math

import pandas as pd
import pytest

from core.funnel.coverage import (
    ACTIVE_CAMPAIGN_COLUMN,
    CAMPAIGN_NOT_FOUND,
    CAMPAIGN_STATE_COLUMN,
    CVR_COLUMN,
    MATCHED_BY_ID,
    MATCHED_BY_NAME,
    SOURCE_CAMPAIGN_COLUMN,
    SUGGESTED_MATCH_COLUMN,
    FunnelInputError,
    OrdersAndSales,
    cover,
    harvest_candidates,
    orders_and_sales,
    product_and_asin,
    suggested_campaigns,
    visible_columns,
)
from core.search_term.frame import add_ratios

EXACT_BRAND = "Luna - B0CYLMJJJC - SP - KW - EXACT - Brand"
PHRASE_CORE = "Luna - B0CYLMJJJC - SP - KW - PHRASE - Core"


def _term(term, campaign, campaign_id, *, clicks, orders, sales, spend, impressions=100, days=7):
    return {"Customer Search Term": term, "Campaign Name": campaign, "Ad Group Name": "AG", "Impressions": impressions,
            "Clicks": clicks, "Spend": spend, f"{days} Day Total Sales": sales, f"{days} Day Total Orders (#)": orders,
            "_campaign_id": campaign_id}


TERMS = [
    _term("luna pajamas", EXACT_BRAND, "1", clicks=30, orders=6, sales=150.0, spend=10.0),
    # The report still names campaign 2 as it was called before a rename.
    _term("luna pajamas", PHRASE_CORE, "2", clicks=10, orders=3, sales=60.0, spend=12.0),
    _term("sleep sack", "Old Broad", "3", clicks=20, orders=0, sales=0.0, spend=15.0),
    _term("baby bag", "Luna - B0CYLM4L23 - SP - KW - BROAD - Old", "9", clicks=5, orders=1, sales=20.0, spend=4.0),
    _term("toy box", EXACT_BRAND, "1", clicks=25, orders=3, sales=30.0, spend=12.0),
]
CAMPAIGNS = pd.DataFrame([
    {"Campaign name": EXACT_BRAND, "Campaign ID": "1", "State": "ENABLED", "Type": "Sponsored Products"},
    {"Campaign name": PHRASE_CORE + " v2", "Campaign ID": "2", "State": "ENABLED", "Type": "Sponsored Products"},
    {"Campaign name": "Old Broad", "Campaign ID": "3", "State": "PAUSED", "Type": "Sponsored Products"},
    {"Campaign name": "Ghost Campaign", "Campaign ID": "4", "State": "ENABLED", "Type": "Sponsored Products"},
])


def _terms(rows=TERMS, days=7):
    return add_ratios(pd.DataFrame(rows), days)


def test_by_campaign_id_a_renamed_campaign_keeps_its_terms():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=True)

    assert coverage.matched_by == MATCHED_BY_ID
    assert coverage.active_terms["Customer Search Term"].tolist() == ["luna pajamas", "luna pajamas", "toy box"]
    assert coverage.gap_terms["Customer Search Term"].tolist() == ["sleep sack", "baby bag"]
    assert coverage.gap_terms[CAMPAIGN_STATE_COLUMN].tolist() == ["PAUSED", CAMPAIGN_NOT_FOUND]
    assert coverage.idle_campaigns["Campaign name"].tolist() == ["Ghost Campaign"]
    assert (len(coverage.active_campaigns), coverage.paused_campaigns) == (3, 1)


def test_by_name_the_renamed_campaign_looks_idle_and_its_terms_look_orphaned():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=False)

    assert coverage.matched_by == MATCHED_BY_NAME
    assert coverage.gap_terms["Campaign Name"].tolist() == [PHRASE_CORE, "Old Broad",
                                                           "Luna - B0CYLM4L23 - SP - KW - BROAD - Old"]
    assert coverage.idle_campaigns["Campaign name"].tolist() == [PHRASE_CORE + " v2", "Ghost Campaign"]


def test_a_file_without_campaign_ids_is_crossed_by_name_even_when_asked_for_ids():
    coverage = cover(_terms(), CAMPAIGNS.drop(columns=["Campaign ID"]), match_by_id=True)

    assert coverage.matched_by == MATCHED_BY_NAME


def test_names_match_whatever_their_case_and_spacing():
    campaigns = pd.DataFrame([{"Campaign name": "  " + EXACT_BRAND.upper(), "State": "enabled"}])

    coverage = cover(_terms(TERMS[:1]), campaigns, match_by_id=False)

    assert len(coverage.active_terms) == 1 and coverage.idle_campaigns.empty


def test_only_sponsored_products_campaigns_are_crossed_because_the_report_has_only_their_terms():
    campaigns = pd.concat([CAMPAIGNS, pd.DataFrame([
        {"Campaign name": "Brand Video", "Campaign ID": "7", "State": "ENABLED", "Type": "Sponsored Brands"},
        {"Campaign name": "Retargeting", "Campaign ID": "8", "State": "ENABLED", "Type": "Sponsored Display"},
    ])], ignore_index=True)

    coverage = cover(_terms(), campaigns, match_by_id=True)

    assert coverage.other_products == 2
    assert "Brand Video" not in coverage.idle_campaigns["Campaign name"].tolist()
    assert len(coverage.campaigns) == 4


def test_without_a_state_column_every_campaign_counts_as_active():
    coverage = cover(_terms(), CAMPAIGNS.drop(columns=["State"]), match_by_id=True)

    assert len(coverage.active_campaigns) == 4 and coverage.paused_campaigns == 0


def test_missing_columns_are_said_in_words_for_the_am():
    with pytest.raises(FunnelInputError, match="search term y de campaña"):
        cover(_terms().drop(columns=["Campaign Name"]), CAMPAIGNS, match_by_id=True)
    with pytest.raises(FunnelInputError, match="Campaign name"):
        cover(_terms(), CAMPAIGNS.drop(columns=["Campaign name"]), match_by_id=True)


def test_harvest_sums_a_term_over_its_campaigns_and_recomputes_its_ratios():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=True)

    harvest = harvest_candidates(_terms(), coverage, min_orders=3)

    assert harvest["Customer Search Term"].tolist() == ["luna pajamas", "toy box"]
    pajamas = harvest.iloc[0]
    assert pajamas[SOURCE_CAMPAIGN_COLUMN] == f"{EXACT_BRAND} | {PHRASE_CORE}"
    assert (pajamas["7 Day Total Orders (#)"], pajamas["Clicks"]) == (9, 40)
    # 22 spent over 210 sold; 9 orders over 40 clicks.
    assert pajamas["Total Advertising Cost of Sales (ACoS)"] == 10.48
    assert pajamas[CVR_COLUMN] == 22.5
    assert harvest[SUGGESTED_MATCH_COLUMN].tolist() == ["Exact", "Phrase"]


def test_harvest_says_whether_a_term_still_runs_in_an_active_campaign():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=True)

    harvest = harvest_candidates(_terms(), coverage, min_orders=1)

    # baby bag only sold in campaign 9, which the account no longer has.
    assert dict(zip(harvest["Customer Search Term"], harvest[ACTIVE_CAMPAIGN_COLUMN])) == {
        "luna pajamas": True, "toy box": True, "baby bag": False}


def test_orders_and_sales_split_the_active_campaigns_from_the_paused_or_missing_ones():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=True)

    assert orders_and_sales(coverage.active_terms, coverage.columns) == OrdersAndSales(orders=12, sales=240)
    assert orders_and_sales(coverage.gap_terms, coverage.columns) == OrdersAndSales(orders=1, sales=20)


def test_orders_and_sales_leave_out_a_column_the_report_lacks():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=True)

    assert orders_and_sales(coverage.gap_terms, {**coverage.columns, "sales": None}) == OrdersAndSales(
        orders=1, sales=None)


def test_harvest_goes_to_exact_under_25_percent_acos_or_at_three_times_the_minimum():
    rows = [_term("cheap", EXACT_BRAND, "1", clicks=20, orders=3, sales=100.0, spend=25.0),
            _term("volume", EXACT_BRAND, "1", clicks=90, orders=9, sales=50.0, spend=60.0),
            _term("pricey", EXACT_BRAND, "1", clicks=30, orders=4, sales=40.0, spend=30.0)]
    frame = _terms(rows)

    harvest = harvest_candidates(frame, cover(frame, CAMPAIGNS, match_by_id=True), min_orders=3)

    assert dict(zip(harvest["Customer Search Term"], harvest[SUGGESTED_MATCH_COLUMN])) == {
        "volume": "Exact", "pricey": "Phrase", "cheap": "Exact"}


def test_harvest_reads_the_14_day_columns_of_a_vendor_account():
    frame = _terms([_term("luna pajamas", EXACT_BRAND, "1", clicks=30, orders=6, sales=150.0, spend=10.0, days=14)],
                   days=14)

    harvest = harvest_candidates(frame, cover(frame, CAMPAIGNS, match_by_id=True), min_orders=3)

    assert harvest["14 Day Total Orders (#)"].tolist() == [6]


def test_harvest_keeps_the_acos_column_name_of_a_legacy_console_file():
    legacy = pd.DataFrame([{"Customer Search Term": "luna pajamas", "Campaign Name": EXACT_BRAND, "Impressions": 800,
                            "Clicks": 30, "Spend": 10.0, "7 Day Total Sales ": 150.0,
                            "Total Advertising Cost of Sales (ACOS) ": 6.67, "7 Day Total Orders (#)": 6,
                            "7 Day Conversion Rate": 20.0}])

    harvest = harvest_candidates(legacy, cover(legacy, CAMPAIGNS, match_by_id=False), min_orders=3)

    assert harvest["Total Advertising Cost of Sales (ACOS) "].tolist() == [6.67]


def test_a_term_without_sales_has_no_acos_and_harvests_as_phrase():
    frame = _terms([_term("odd", EXACT_BRAND, "1", clicks=10, orders=3, sales=0.0, spend=5.0)])

    harvest = harvest_candidates(frame, cover(frame, CAMPAIGNS, match_by_id=True), min_orders=3)

    assert math.isnan(harvest["Total Advertising Cost of Sales (ACoS)"].iloc[0])
    assert harvest[SUGGESTED_MATCH_COLUMN].tolist() == ["Phrase"]


def test_without_an_orders_column_there_is_no_harvest():
    frame = _terms().drop(columns=["7 Day Total Orders (#)"])

    with pytest.raises(FunnelInputError, match="órdenes"):
        harvest_candidates(frame, cover(frame, CAMPAIGNS, match_by_id=True), min_orders=3)


def test_suggested_campaigns_take_product_and_asin_from_the_old_campaign_and_rank_by_spend():
    coverage = cover(_terms(), CAMPAIGNS, match_by_id=True)

    suggested = suggested_campaigns(coverage.gap_terms, coverage.columns, "Exact")

    assert suggested["Nombre sugerido"].tolist() == [
        "[Producto] - [ASIN] - SP - KW - Exact - Sleep Sack",
        "Luna - B0CYLM4L23 - SP - KW - Exact - Baby Bag",
    ]
    assert suggested[CAMPAIGN_STATE_COLUMN].tolist() == ["PAUSED", CAMPAIGN_NOT_FOUND]
    assert suggested[["Clicks", "Spend", "Orders", "Sales"]].values.tolist() == [[20, 15, 0, 0], [5, 4, 1, 20]]


def test_without_gap_terms_there_is_nothing_to_suggest():
    coverage = cover(_terms(TERMS[:2]), CAMPAIGNS, match_by_id=True)

    assert suggested_campaigns(coverage.gap_terms, coverage.columns, "Phrase").empty


@pytest.mark.parametrize("name, expected", [
    ("Luna - B0CYLMJJJC - SP - KW - EXACT - Brand", ("Luna", "B0CYLMJJJC")),
    ("dermaglos-b0cylm4l23-SP", ("dermaglos", "B0CYLM4L23")),
    ("Brand Defensive", (None, None)),
    (float("nan"), (None, None)),
])
def test_product_and_asin_come_from_the_campaign_name(name, expected):
    assert product_and_asin(name) == expected


def test_hidden_ids_never_reach_a_table():
    assert list(visible_columns(_terms()).columns) == [column for column in _terms().columns
                                                       if not column.startswith("_")]

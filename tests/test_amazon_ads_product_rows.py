"""product_rows: SP/SB/SD targeting and SB/SD campaign reports mapped to table rows. Synthetic rows only."""
from __future__ import annotations

import dataclasses
import gzip
import json
from collections.abc import Callable
from datetime import date
from typing import NamedTuple

import pytest

from core.amazon_ads.product_rows import (
    SB_CAMPAIGN_ROWS,
    SB_CAMPAIGN_SPEC,
    SB_LEGACY_CAMPAIGN_ROWS,
    SB_LEGACY_CAMPAIGN_SPEC,
    SB_TARGETING_ROWS,
    SB_TARGETING_SPEC,
    SD_CAMPAIGN_ROWS,
    SD_CAMPAIGN_SPEC,
    SD_TARGETING_ROWS,
    SD_TARGETING_SPEC,
    SP_TARGETING_ROWS,
    SP_TARGETING_SPEC,
    ReportRowsError,
)

WINDOW_START = date(2026, 9, 8)
WINDOW_END = date(2026, 9, 10)

TARGET_METRICS = ("impressions", "clicks", "cost", "purchases_7d", "sales_7d", "purchases_14d", "sales_14d",
                  "purchases", "sales", "purchases_clicks", "sales_clicks")
CAMPAIGN_METRICS = ("impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks", "sales_clicks",
                    "new_to_brand_purchases", "new_to_brand_sales", "viewable_impressions")
MONEY_COLUMNS = frozenset({"cost", "sales_7d", "sales_14d", "sales", "sales_clicks", "new_to_brand_sales"})
# The day is written with jsonb_populate_recordset, so a key missing from a row would land as NULL.
TARGET_COLUMNS = frozenset({"profile_id", "report_date", "ad_product", "target_id", "campaign_id", "ad_group_id",
                            "target_kind", "target_text", "match_type", *TARGET_METRICS, "top_of_search_is",
                            "currency_code"})
CAMPAIGN_COLUMNS = frozenset({"profile_id", "report_date", "ad_product", "campaign_id", *CAMPAIGN_METRICS,
                              "top_of_search_is", "cost_type", "budget_amount", "currency_code"})
_ABSENT = object()


def _sp_target_row(**overrides) -> dict:
    row = {
        "date": "2026-09-08",
        "campaignId": 101,
        "adGroupId": 201,
        "keywordId": 301,
        "keyword": "demo keyword",
        "keywordType": "EXACT",
        "matchType": "EXACT",
        "targeting": "demo keyword",
        "impressions": 1200,
        "clicks": 34,
        "cost": 21.5,
        "purchases7d": 3,
        "sales7d": 89.97,
        "purchases14d": 4,
        "sales14d": 119.96,
        "topOfSearchImpressionShare": 4.38,
    }
    row.update(overrides)
    return row


def _sb_campaign_row(**overrides) -> dict:
    row = {
        "date": "2026-09-08",
        "campaignId": 102,
        "impressions": 900,
        "clicks": 12,
        "cost": 8.4,
        "purchases": 3,
        "sales": 89.97,
        "purchasesClicks": 2,
        "salesClicks": 59.98,
        "costType": "CPC",
        "viewableImpressions": 450,
        "campaignBudgetAmount": 20.0,
        "campaignBudgetCurrencyCode": "USD",
        "topOfSearchImpressionShare": 6.5,
        "newToBrandPurchases": 1,
        "newToBrandSales": 29.99,
    }
    row.update(overrides)
    return row


def _sb_target_row(**overrides) -> dict:
    row = {
        "date": "2026-09-08",
        "campaignId": 103,
        "adGroupId": 203,
        "keywordId": 303,
        "keywordText": 'category="1000"',
        "keywordType": "TARGETING_EXPRESSION",
        "matchType": "TARGETING_EXPRESSION",
        "targetingExpression": 'category="1000"',
        "targetingText": 'category="Demo Category"',
        "impressions": 136,
        "clicks": 3,
        "cost": 2.22,
        "purchases": 2,
        "sales": 61.98,
        "purchasesClicks": 1,
        "salesClicks": 30.99,
    }
    row.update(overrides)
    return row


def _sd_campaign_row(**overrides) -> dict:
    row = {
        "date": "2026-09-08",
        "campaignId": 104,
        "impressions": 18000,
        "impressionsViews": 5000,
        "clicks": 12,
        "cost": 25.46,
        "purchases": 4,
        "sales": 115.57,
        "purchasesClicks": 1,
        "salesClicks": 28.6,
        "costType": "VCPM",
        "campaignBudgetAmount": 39.0,
        "campaignBudgetCurrencyCode": "USD",
        "newToBrandPurchases": 3,
        "newToBrandSales": 86.97,
    }
    row.update(overrides)
    return row


def _sd_target_row(**overrides) -> dict:
    row = {
        "date": "2026-09-08",
        "campaignId": 105,
        "adGroupId": 205,
        "targetingId": 305,
        "targetingExpression": 'asin="B000DEMO01"',
        "targetingText": 'asin="B000DEMO01"',
        "impressions": 300,
        "clicks": 5,
        "cost": 1.5,
        "purchases": 2,
        "sales": 39.98,
        "purchasesClicks": 1,
        "salesClicks": 19.99,
    }
    row.update(overrides)
    return row


class _Report(NamedTuple):
    parser: object
    api_row: Callable[..., dict]
    ids: dict            # id column -> report field, the table's key first
    columns: frozenset

    @property
    def key_column(self) -> str:
        return next(iter(self.ids))

    @property
    def key_field(self) -> str:
        return self.ids[self.key_column]


_TARGET_IDS = {"campaign_id": "campaignId", "ad_group_id": "adGroupId"}
SP_TARGETING = _Report(SP_TARGETING_ROWS, _sp_target_row, {"target_id": "keywordId", **_TARGET_IDS}, TARGET_COLUMNS)
SB_CAMPAIGNS = _Report(SB_CAMPAIGN_ROWS, _sb_campaign_row, {"campaign_id": "campaignId"}, CAMPAIGN_COLUMNS)
SB_TARGETING = _Report(SB_TARGETING_ROWS, _sb_target_row, {"target_id": "keywordId", **_TARGET_IDS}, TARGET_COLUMNS)
SD_CAMPAIGNS = _Report(SD_CAMPAIGN_ROWS, _sd_campaign_row, {"campaign_id": "campaignId"}, CAMPAIGN_COLUMNS)
SD_TARGETING = _Report(SD_TARGETING_ROWS, _sd_target_row, {"target_id": "targetingId", **_TARGET_IDS},
                       TARGET_COLUMNS)


def _each(*reports):
    return pytest.mark.parametrize("report", reports, ids=[report.parser.spec.report_type_id for report in reports])


every_report = _each(SP_TARGETING, SB_CAMPAIGNS, SB_TARGETING, SD_CAMPAIGNS, SD_TARGETING)


def _mapped(report, api_rows, **overrides):
    options = {"profile_id": "555", "currency_code": "USD", "window_start": WINDOW_START, "window_end": WINDOW_END}
    options.update(overrides)
    return report.parser.rows_by_day(api_rows, **options)


def _row(report, api_row, **overrides) -> dict:
    (row,) = _mapped(report, [api_row], **overrides)[WINDOW_START]
    return row


@pytest.mark.parametrize("parser, spec, report_type_id, ad_product, group_by, retention_days, columns", [
    pytest.param(SP_TARGETING_ROWS, SP_TARGETING_SPEC, "spTargeting", "SPONSORED_PRODUCTS", ("targeting",), 95,
                 ("date", "campaignId", "adGroupId", "keywordId", "keyword", "keywordType", "matchType", "targeting",
                  "impressions", "clicks", "cost", "purchases7d", "sales7d", "purchases14d", "sales14d",
                  "topOfSearchImpressionShare"), id="spTargeting"),
    pytest.param(SB_CAMPAIGN_ROWS, SB_CAMPAIGN_SPEC, "sbCampaigns", "SPONSORED_BRANDS", ("campaign",), 60,
                 ("date", "campaignId", "impressions", "clicks", "cost", "purchases", "sales", "purchasesClicks",
                  "salesClicks", "costType", "viewableImpressions", "campaignBudgetAmount",
                  "campaignBudgetCurrencyCode", "topOfSearchImpressionShare", "newToBrandPurchases",
                  "newToBrandSales"), id="sbCampaigns"),
    pytest.param(SB_TARGETING_ROWS, SB_TARGETING_SPEC, "sbTargeting", "SPONSORED_BRANDS", ("targeting",), 60,
                 ("date", "campaignId", "adGroupId", "keywordId", "keywordText", "keywordType", "matchType",
                  "targetingExpression", "targetingText", "impressions", "clicks", "cost", "purchases", "sales",
                  "purchasesClicks", "salesClicks"), id="sbTargeting"),
    pytest.param(SD_CAMPAIGN_ROWS, SD_CAMPAIGN_SPEC, "sdCampaigns", "SPONSORED_DISPLAY", ("campaign",), 65,
                 ("date", "campaignId", "impressions", "impressionsViews", "clicks", "cost", "purchases", "sales",
                  "purchasesClicks", "salesClicks", "costType", "campaignBudgetAmount",
                  "campaignBudgetCurrencyCode", "newToBrandPurchases", "newToBrandSales"), id="sdCampaigns"),
    pytest.param(SD_TARGETING_ROWS, SD_TARGETING_SPEC, "sdTargeting", "SPONSORED_DISPLAY", ("targeting",), 65,
                 ("date", "campaignId", "adGroupId", "targetingId", "targetingExpression", "targetingText",
                  "impressions", "clicks", "cost", "purchases", "sales", "purchasesClicks", "salesClicks"),
                 id="sdTargeting"),
])
def test_each_report_asks_amazon_for_exactly_the_columns_it_accepted(parser, spec, report_type_id, ad_product,
                                                                      group_by, retention_days, columns):
    assert parser.spec is spec
    assert (spec.report_type_id, spec.ad_product, spec.group_by, spec.time_unit, spec.retention_days) == \
        (report_type_id, ad_product, group_by, "DAILY", retention_days)
    assert spec.columns == columns


def test_a_parser_cannot_drift_from_the_columns_its_spec_asks_for():
    without_share = dataclasses.replace(SP_TARGETING_SPEC, columns=SP_TARGETING_SPEC.columns[:-1])
    with_a_name = dataclasses.replace(SB_CAMPAIGN_SPEC, columns=(*SB_CAMPAIGN_SPEC.columns, "campaignName"))

    with pytest.raises(ValueError, match="topOfSearchImpressionShare"):
        dataclasses.replace(SP_TARGETING_ROWS, spec=without_share)
    with pytest.raises(ValueError, match="campaignName"):
        dataclasses.replace(SB_CAMPAIGN_ROWS, spec=with_a_name)


def test_sp_targeting_fields_land_on_the_target_table():
    row = _row(SP_TARGETING, _sp_target_row(), currency_code="usd")

    assert row == {
        "profile_id": "555",
        "report_date": "2026-09-08",
        "ad_product": "SP",
        "target_id": "301",
        "campaign_id": "101",
        "ad_group_id": "201",
        "target_kind": "keyword",
        "target_text": "demo keyword",
        "match_type": "EXACT",
        "impressions": 1200,
        "clicks": 34,
        "cost": 21.5,
        "purchases_7d": 3,
        "sales_7d": 89.97,
        "purchases_14d": 4,
        "sales_14d": 119.96,
        "purchases": 0,
        "sales": 0.0,
        "purchases_clicks": 0,
        "sales_clicks": 0.0,
        # A 0-100 percentage, the scale the real API answers in.
        "top_of_search_is": 4.38,
        "currency_code": "USD",
    }


def test_sb_targeting_fields_land_on_the_target_table():
    row = _row(SB_TARGETING, _sb_target_row())

    assert row == {
        "profile_id": "555",
        "report_date": "2026-09-08",
        "ad_product": "SB",
        "target_id": "303",
        "campaign_id": "103",
        "ad_group_id": "203",
        "target_kind": "product",
        # The readable text, not keywordText's category id.
        "target_text": 'category="Demo Category"',
        "match_type": "",
        "impressions": 136,
        "clicks": 3,
        "cost": 2.22,
        "purchases_7d": 0,
        "sales_7d": 0.0,
        "purchases_14d": 0,
        "sales_14d": 0.0,
        "purchases": 2,
        "sales": 61.98,
        "purchases_clicks": 1,
        "sales_clicks": 30.99,
        "top_of_search_is": None,
        "currency_code": "USD",
    }


def test_sd_targeting_fields_land_on_the_target_table():
    row = _row(SD_TARGETING, _sd_target_row())

    assert row == {
        "profile_id": "555",
        "report_date": "2026-09-08",
        "ad_product": "SD",
        "target_id": "305",
        "campaign_id": "105",
        "ad_group_id": "205",
        "target_kind": "product",
        "target_text": 'asin="B000DEMO01"',
        "match_type": "",
        "impressions": 300,
        "clicks": 5,
        "cost": 1.5,
        "purchases_7d": 0,
        "sales_7d": 0.0,
        "purchases_14d": 0,
        "sales_14d": 0.0,
        "purchases": 2,
        "sales": 39.98,
        "purchases_clicks": 1,
        "sales_clicks": 19.99,
        "top_of_search_is": None,
        "currency_code": "USD",
    }


def test_sb_campaign_fields_land_on_the_campaign_table():
    row = _row(SB_CAMPAIGNS, _sb_campaign_row())

    assert row == {
        "profile_id": "555",
        "report_date": "2026-09-08",
        "ad_product": "SB",
        "campaign_id": "102",
        "impressions": 900,
        "clicks": 12,
        "cost": 8.4,
        "purchases": 3,
        "sales": 89.97,
        "purchases_clicks": 2,
        "sales_clicks": 59.98,
        "new_to_brand_purchases": 1,
        "new_to_brand_sales": 29.99,
        "viewable_impressions": 450,
        "top_of_search_is": 6.5,
        "cost_type": "CPC",
        "budget_amount": 20.0,
        "currency_code": "USD",
    }


def test_sd_campaign_fields_land_on_the_campaign_table():
    row = _row(SD_CAMPAIGNS, _sd_campaign_row())

    assert row == {
        "profile_id": "555",
        "report_date": "2026-09-08",
        "ad_product": "SD",
        "campaign_id": "104",
        "impressions": 18000,
        "clicks": 12,
        "cost": 25.46,
        "purchases": 4,
        "sales": 115.57,
        "purchases_clicks": 1,
        "sales_clicks": 28.6,
        # SD reports no top-of-search share, and calls viewable impressions impressionsViews.
        "new_to_brand_purchases": 3,
        "new_to_brand_sales": 86.97,
        "viewable_impressions": 5000,
        "top_of_search_is": None,
        "cost_type": "VCPM",
        "budget_amount": 39.0,
        "currency_code": "USD",
    }


@every_report
def test_every_row_carries_every_column_of_its_table_even_from_a_sparse_row(report):
    full = _row(report, report.api_row())
    sparse = _row(report, {"date": "2026-09-08", report.key_field: 7})

    assert set(full) == set(sparse) == report.columns
    assert all(sparse[column] == 0 for column in report.columns & {*TARGET_METRICS, *CAMPAIGN_METRICS})
    assert all(sparse[column] is None for column in report.columns & {"top_of_search_is", "budget_amount"})
    json.dumps([full, sparse])


@every_report
def test_counts_are_whole_numbers_and_money_keeps_four_decimals(report):
    row = _row(report, report.api_row(clicks=3.0, cost=1.123456))

    assert (row["clicks"], row["cost"]) == (3, 1.1235)
    metrics = report.columns & {*TARGET_METRICS, *CAMPAIGN_METRICS}
    assert all(type(row[column]) is (float if column in MONEY_COLUMNS else int) for column in metrics)


@pytest.mark.parametrize("keyword_type, kind, match_type", [
    ("BROAD", "keyword", "BROAD"),
    ("PHRASE", "keyword", "PHRASE"),
    ("EXACT", "keyword", "EXACT"),
    ("TARGETING_EXPRESSION", "product", ""),
    ("TARGETING_EXPRESSION_PREDEFINED", "auto", ""),
])
def test_sp_keyword_type_gives_the_target_kind_and_match_type(keyword_type, kind, match_type):
    row = _row(SP_TARGETING, _sp_target_row(keywordType=keyword_type, matchType=keyword_type))

    assert (row["target_kind"], row["match_type"]) == (kind, match_type)


@pytest.mark.parametrize("keyword_type, text, kind, match_type", [
    ("BROAD", "demo keyword", "keyword", "BROAD"),
    ("PHRASE", "demo keyword", "keyword", "PHRASE"),
    ("EXACT", "demo keyword", "keyword", "EXACT"),
    ("TARGETING_EXPRESSION", 'asin="B000DEMO02"', "product", ""),
    ("THEME", "keywords-related-to-your-brand", "theme", ""),
])
def test_sb_keyword_type_gives_the_target_kind_and_match_type(keyword_type, text, kind, match_type):
    row = _row(SB_TARGETING, _sb_target_row(keywordType=keyword_type, matchType=keyword_type, keywordText=text,
                                            targetingExpression=text, targetingText=text))

    assert (row["target_kind"], row["target_text"], row["match_type"]) == (kind, text, match_type)


@_each(SP_TARGETING, SB_TARGETING)
def test_the_match_type_field_speaks_only_when_the_keyword_type_is_missing(report):
    row = _row(report, report.api_row(keywordType=None, matchType="phrase"))

    assert (row["target_kind"], row["match_type"]) == ("keyword", "PHRASE")


@_each(SP_TARGETING, SB_TARGETING)
def test_a_keyword_type_amazon_adds_later_is_kept_as_a_product_target(report):
    row = _row(report, report.api_row(keywordType="SOMETHING_NEW", matchType="SOMETHING_NEW"))

    assert (row["target_kind"], row["match_type"]) == ("product", "")


@pytest.mark.parametrize("expression, kind", [
    ('asin="B000DEMO01"', "product"),
    ('category="1000"', "product"),
    ('category="1000" brand="Demo"', "product"),
    ("similarProduct", "auto"),
    ("views=(exactProduct lookback=30)", "audience"),
    ("views=(similarProduct lookback=30)", "audience"),
    ("purchases=(relatedProduct lookback=180)", "audience"),
    ('audience="Demo in-market"', "audience"),
    ("", "product"),
])
def test_sd_expression_gives_the_target_kind(expression, kind):
    row = _row(SD_TARGETING, _sd_target_row(targetingExpression=expression, targetingText="Demo target"))

    assert (row["target_kind"], row["match_type"]) == (kind, "")


@pytest.mark.parametrize("report, overrides, text", [
    pytest.param(SP_TARGETING, {"targeting": None, "keyword": "demo fallback"}, "demo fallback", id="sp-keyword"),
    pytest.param(SB_TARGETING, {"targetingText": "", "keywordText": "demo keyword text"}, "demo keyword text",
                 id="sb-keyword-text"),
    pytest.param(SB_TARGETING, {"targetingText": None, "keywordText": None, "targetingExpression": "demo expression"},
                 "demo expression", id="sb-expression"),
    pytest.param(SD_TARGETING, {"targetingText": None, "targetingExpression": 'asin="B000DEMO03"'},
                 'asin="B000DEMO03"', id="sd-expression"),
])
def test_the_target_text_falls_back_when_the_readable_one_is_missing(report, overrides, text):
    assert _row(report, report.api_row(**overrides))["target_text"] == text


@_each(SP_TARGETING, SB_TARGETING, SD_TARGETING)
def test_targeting_rows_carry_the_profile_currency(report):
    # None of the targeting reports has a currency column.
    assert _row(report, report.api_row(), currency_code="mxn")["currency_code"] == "MXN"


@_each(SB_CAMPAIGNS, SD_CAMPAIGNS)
def test_campaign_rows_carry_their_budget_currency_and_fall_back_to_the_profile(report):
    assert _row(report, report.api_row(campaignBudgetCurrencyCode="usd"), currency_code="mxn")["currency_code"] == \
        "USD"
    assert _row(report, report.api_row(campaignBudgetCurrencyCode=None), currency_code="mxn")["currency_code"] == \
        "MXN"


@_each(SB_CAMPAIGNS, SD_CAMPAIGNS)
def test_the_cost_type_is_upper_case_and_empty_when_missing(report):
    assert _row(report, report.api_row(costType=" vcpm "))["cost_type"] == "VCPM"
    assert _row(report, report.api_row(costType=None))["cost_type"] == ""


@every_report
def test_every_day_of_the_window_is_a_key_even_with_no_rows(report):
    by_day = _mapped(report, [report.api_row(date="2026-09-09")])

    assert list(by_day) == [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    assert by_day[date(2026, 9, 8)] == [] and by_day[date(2026, 9, 10)] == []
    assert len(by_day[date(2026, 9, 9)]) == 1
    assert _mapped(report, []) == {date(2026, 9, 8): [], date(2026, 9, 9): [], date(2026, 9, 10): []}


def test_day_positions_group_rows_by_day_and_one_day_is_built_at_a_time():
    api_rows = [_sd_target_row(date="2026-09-10"), _sd_target_row(date="2026-09-08", clicks=1),
                _sd_target_row(date="2026-09-10", clicks=6)]
    report_rows = SD_TARGETING_ROWS.compact_rows(api_rows)

    positions_by_day = SD_TARGETING_ROWS.day_row_positions(report_rows, window_start=WINDOW_START,
                                                           window_end=WINDOW_END)

    assert positions_by_day == {date(2026, 9, 8): [1], date(2026, 9, 9): [], date(2026, 9, 10): [0, 2]}
    rows = SD_TARGETING_ROWS.day_rows(report_rows, positions_by_day[date(2026, 9, 10)], profile_id="555",
                                      currency_code="USD", day=date(2026, 9, 10))
    assert rows == _mapped(SD_TARGETING, api_rows)[date(2026, 9, 10)]
    assert len(rows) == 1 and rows[0]["clicks"] == 11


@every_report
def test_ids_are_exact_text_even_at_eighteen_digits(report, tmp_path):
    # Newer SB entities have 18-digit ids. They arrive as JSON integers and must never pass through a float.
    big_ids = {field: 144000000000000100 + offset for offset, field in enumerate(report.ids.values())}
    report_path = tmp_path / "report.json.gz"
    with gzip.open(report_path, "wt", encoding="utf-8") as report_file:
        json.dump([report.api_row(**big_ids)], report_file)

    report_rows = report.parser.load_compact_report(report_path)
    (row,) = report.parser.day_rows(report_rows, [0], profile_id="555", currency_code="USD", day=WINDOW_START)

    assert {column: row[column] for column in report.ids} == \
        {column: str(big_ids[field]) for column, field in report.ids.items()}


@every_report
def test_numeric_ids_never_come_out_in_float_notation(report):
    row = _row(report, report.api_row(**{field: 218190823249654.0 for field in report.ids.values()}))

    assert all(row[column] == "218190823249654" for column in report.ids)


@every_report
def test_a_missing_metric_reads_as_zero_and_a_missing_fact_as_unknown(report):
    missing_facts = {field: None for field in ("topOfSearchImpressionShare", "campaignBudgetAmount")
                     if field in report.parser.spec.columns}

    row = _row(report, report.api_row(clicks=None, cost="", **missing_facts))

    assert (row["clicks"], row["cost"]) == (0, 0.0)
    assert row["top_of_search_is"] is None and row.get("budget_amount") is None


@every_report
def test_repeated_key_rows_in_one_day_are_summed(report):
    single = _row(report, report.api_row())

    (merged,) = _mapped(report, [report.api_row(), report.api_row()])[WINDOW_START]

    metrics = report.columns & {*TARGET_METRICS, *CAMPAIGN_METRICS}
    assert {column: merged[column] for column in metrics} == \
        pytest.approx({column: 2 * single[column] for column in metrics})
    assert merged["top_of_search_is"] == single["top_of_search_is"]


@every_report
def test_rows_of_another_key_or_another_day_are_not_merged(report):
    by_day = _mapped(report, [report.api_row(), report.api_row(**{report.key_field: 999}),
                              report.api_row(date="2026-09-09")])

    first_key = str(report.api_row()[report.key_field])
    assert sorted(row[report.key_column] for row in by_day[WINDOW_START]) == sorted([first_key, "999"])
    assert [row[report.key_column] for row in by_day[date(2026, 9, 9)]] == [first_key]


@_each(SP_TARGETING, SB_CAMPAIGNS)
def test_repeated_rows_weight_the_share_by_impressions_and_an_unknown_share_is_not_zero(report):
    (row,) = _mapped(report, [
        report.api_row(impressions=300, topOfSearchImpressionShare=10.0),
        report.api_row(impressions=100, topOfSearchImpressionShare=2.0),
        report.api_row(impressions=500, topOfSearchImpressionShare=None),
    ])[WINDOW_START]

    assert row["top_of_search_is"] == pytest.approx((10.0 * 300 + 2.0 * 100) / 400)
    assert row["impressions"] == 900


@_each(SP_TARGETING, SB_CAMPAIGNS)
def test_a_negative_duplicate_row_cannot_push_the_merged_share_out_of_0_to_100(report):
    (row,) = _mapped(report, [
        report.api_row(impressions=1000, topOfSearchImpressionShare=100.0),
        report.api_row(impressions=-999, topOfSearchImpressionShare=0.0),
    ])[WINDOW_START]

    assert row["impressions"] == 1000
    assert row["top_of_search_is"] == pytest.approx(100.0)


@_each(SB_CAMPAIGNS, SD_CAMPAIGNS)
def test_repeated_campaign_rows_keep_the_largest_known_budget_and_the_first_cost_type(report):
    (row,) = _mapped(report, [
        report.api_row(campaignBudgetAmount=None, costType=None),
        report.api_row(campaignBudgetAmount=15.0, costType="CPC"),
        report.api_row(campaignBudgetAmount=25.0, costType="VCPM"),
    ])[WINDOW_START]

    assert (row["budget_amount"], row["cost_type"]) == (25.0, "CPC")


@every_report
def test_values_below_zero_are_stored_as_zero_with_one_warning_per_report(report, caplog):
    # The real case: Amazon netted invalid traffic out of a day with nothing else and sent impressions -2.
    adjustment = report.api_row(date="2026-09-09", impressions=-2, clicks=0, cost=-0.5)

    with caplog.at_level("WARNING", logger="core.amazon_ads.product_rows"):
        by_day = _mapped(report, [report.api_row(), adjustment, report.api_row(date="2026-09-10", clicks=-1)])

    (row,) = by_day[date(2026, 9, 9)]
    assert (row["impressions"], row["clicks"], row["cost"]) == (0, 0, 0.0)
    assert by_day[date(2026, 9, 10)][0]["clicks"] == 0
    assert by_day[WINDOW_START][0]["impressions"] > 0
    warnings = [record for record in caplog.records if record.name == "core.amazon_ads.product_rows"]
    assert len(warnings) == 1
    assert f"{report.parser.spec.report_type_id} report" in caplog.text
    assert "3 values below zero" in caplog.text and "impressions=-2" in caplog.text


@every_report
def test_every_metric_below_zero_is_stored_as_zero(report):
    row = _row(report, report.api_row(**{field: -1.5 for field in report.parser.metrics.values()}))

    assert all(row[column] == 0 for column in report.columns & {*TARGET_METRICS, *CAMPAIGN_METRICS})


@pytest.mark.parametrize("report, fields", [
    pytest.param(SP_TARGETING, {"topOfSearchImpressionShare": "top_of_search_is"}, id="spTargeting"),
    pytest.param(SB_CAMPAIGNS, {"campaignBudgetAmount": "budget_amount",
                                "topOfSearchImpressionShare": "top_of_search_is"}, id="sbCampaigns"),
    pytest.param(SD_CAMPAIGNS, {"campaignBudgetAmount": "budget_amount"}, id="sdCampaigns"),
])
def test_a_budget_or_share_below_zero_is_unknown_and_a_non_numeric_one_refuses_the_report(report, fields):
    row = _row(report, report.api_row(**{field: -5.0 for field in fields}))

    assert all(row[column] is None for column in fields.values())
    for field in fields:
        with pytest.raises(ReportRowsError, match=f"non-numeric {field}"):
            _mapped(report, [report.api_row(**{field: "high"})])
        with pytest.raises(ReportRowsError, match=f"impossible {field}"):
            _mapped(report, [report.api_row(**{field: float("inf")})])


@every_report
@pytest.mark.parametrize("field, value, message", [
    ("cost", float("nan"), "impossible cost"),
    ("cost", float("inf"), "impossible cost"),
    ("cost", float("-inf"), "impossible cost"),
    ("clicks", "many", "non-numeric clicks"),
    ("impressions", True, "non-numeric impressions"),
])
def test_a_metric_that_is_not_a_finite_number_refuses_the_report(report, field, value, message):
    with pytest.raises(ReportRowsError, match=message):
        _mapped(report, [report.api_row(**{field: value})])


@every_report
@pytest.mark.parametrize("day, message", [
    ("2026-09-07", "outside"),
    ("2026-09-11", "outside"),
    (None, "no valid date"),
    ("", "no valid date"),
    ("yesterday", "no valid date"),
])
def test_a_row_without_a_date_inside_the_window_is_refused(report, day, message):
    with pytest.raises(ReportRowsError, match=message):
        _mapped(report, [report.api_row(date=day)])


@every_report
@pytest.mark.parametrize("missing", [None, "", _ABSENT], ids=["null", "empty", "absent"])
def test_a_row_without_its_key_id_is_refused(report, missing):
    api_row = report.api_row(**{report.key_field: missing})
    if missing is _ABSENT:
        del api_row[report.key_field]

    with pytest.raises(ReportRowsError, match=f"no {report.key_column.removesuffix('_id')} id"):
        _mapped(report, [report.api_row(), api_row])


@every_report
@pytest.mark.parametrize("unusable", [{"cost": float("nan")}, {"date": "2026-09-11"}, {"clicks": "many"}])
def test_one_unusable_row_on_a_later_day_refuses_the_report_before_any_day(report, unusable):
    report_rows = report.parser.compact_rows([report.api_row(),
                                              report.api_row(**{"date": "2026-09-10", **unusable})])

    with pytest.raises(ReportRowsError):
        report.parser.day_row_positions(report_rows, window_start=WINDOW_START, window_end=WINDOW_END)


def test_a_window_that_ends_before_it_starts_is_refused():
    with pytest.raises(ReportRowsError, match="ends before it starts"):
        _mapped(SB_CAMPAIGNS, [], window_start=WINDOW_END, window_end=WINDOW_START)


@every_report
def test_a_row_that_is_not_an_object_is_refused(report):
    with pytest.raises(ReportRowsError, match="not an object"):
        _mapped(report, [report.api_row(), "not a row"])


@every_report
def test_the_compact_report_holds_only_the_fields_the_spec_asks_for(report, tmp_path):
    report_path = tmp_path / "report.json.gz"
    with gzip.open(report_path, "wt", encoding="utf-8") as report_file:
        json.dump([report.api_row(campaignName="Demo campaign " + "x" * 40, unusedMetric=7777777)], report_file)

    report_rows = report.parser.load_compact_report(report_path)

    assert len(report_rows) == 1 and len(report_rows[0]) == len(report.parser.spec.columns)
    assert 7777777 not in report_rows[0] and not any("x" * 40 in str(value) for value in report_rows[0])
    assert report.parser.day_rows(report_rows, [0], profile_id="555", currency_code="USD", day=WINDOW_START) == \
        _mapped(report, [report.api_row()])[WINDOW_START]


# ── SB's v2 campaign report: the campaigns of the old format ────────────────────


def _v2_row(**overrides) -> dict:
    row = {"campaignId": 144268751860314311, "impressions": 6560, "clicks": 281, "cost": 584.18,
           "attributedConversions14d": 69, "attributedSales14d": 2208.88, "attributedOrdersNewToBrand14d": 12,
           "attributedSalesNewToBrand14d": 380.5}
    row.update(overrides)
    return row


def _v2_rows(api_rows, day=WINDOW_START):
    return SB_LEGACY_CAMPAIGN_ROWS.rows_by_day(api_rows, profile_id="555", currency_code="USD", window_start=day,
                                               window_end=day)[day]


def test_the_v2_report_asks_ids_and_numbers_only():
    # A name or a state among the metrics makes v2 answer every campaign ever made, zeros included.
    assert SB_LEGACY_CAMPAIGN_ROWS.spec is SB_LEGACY_CAMPAIGN_SPEC
    assert (SB_LEGACY_CAMPAIGN_SPEC.ad_product, SB_LEGACY_CAMPAIGN_SPEC.retention_days) == ("SPONSORED_BRANDS", 60)
    assert SB_LEGACY_CAMPAIGN_SPEC.columns == (
        "campaignId", "impressions", "clicks", "cost", "attributedConversions14d", "attributedSales14d",
        "attributedOrdersNewToBrand14d", "attributedSalesNewToBrand14d")


def test_a_v2_row_lands_on_the_campaign_table_with_its_sales_as_click_only_sales_too():
    (row,) = _v2_rows([_v2_row()])

    assert row == {
        "profile_id": "555", "report_date": "2026-09-08", "ad_product": "SB", "campaign_id": "144268751860314311",
        "impressions": 6560, "clicks": 281, "cost": 584.18,
        # v2 refuses view-attributed metrics: its 14-day sales are click-only, so they fill both pairs.
        "purchases": 69, "sales": 2208.88, "purchases_clicks": 69, "sales_clicks": 2208.88,
        "new_to_brand_purchases": 12, "new_to_brand_sales": 380.5, "viewable_impressions": 0,
        "top_of_search_is": None, "cost_type": "", "budget_amount": None, "currency_code": "USD",
    }


def test_a_v2_report_is_one_day_and_its_rows_carry_that_day():
    (row,) = _v2_rows([_v2_row()], day=date(2026, 9, 16))

    assert row["report_date"] == "2026-09-16"
    with pytest.raises(ReportRowsError, match="covers one day"):
        SB_LEGACY_CAMPAIGN_ROWS.rows_by_day([_v2_row()], profile_id="555", currency_code="USD",
                                            window_start=WINDOW_START, window_end=WINDOW_END)


def test_a_campaign_twice_in_a_v2_report_is_summed():
    rows = _v2_rows([_v2_row(cost=10.0, impressions=100), _v2_row(cost=2.5, impressions=20)])

    assert [(row["cost"], row["impressions"]) for row in rows] == [(12.5, 120)]

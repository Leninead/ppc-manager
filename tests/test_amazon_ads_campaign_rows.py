"""spCampaigns report rows mapped to table rows: one day at a time, every row checked first."""
from __future__ import annotations

from datetime import date

import pytest

from core.amazon_ads.campaign_rows import ReportRowsError, rows_by_day

WINDOW_START = date(2026, 9, 8)
WINDOW_END = date(2026, 9, 10)


def _api_row(day="2026-09-08", campaign_id="101", **overrides):
    row = {
        "date": day,
        "campaignId": campaign_id,
        "impressions": 1200,
        "clicks": 34,
        "cost": 21.5,
        "purchases7d": 3,
        "sales7d": 89.97,
        "purchases14d": 4,
        "sales14d": 119.96,
        "campaignBudgetCurrencyCode": "USD",
    }
    row.update(overrides)
    return row


def _mapped(api_rows, **overrides):
    options = {"profile_id": "555", "currency_code": "USD",
               "window_start": WINDOW_START, "window_end": WINDOW_END}
    options.update(overrides)
    return rows_by_day(api_rows, **options)


def test_every_day_of_the_window_is_a_key_even_with_no_rows():
    by_day = _mapped([_api_row(day="2026-09-09")])

    assert sorted(by_day) == [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    assert by_day[date(2026, 9, 8)] == []
    assert len(by_day[date(2026, 9, 9)]) == 1


def test_metrics_and_keys_land_on_the_table_columns():
    row = _mapped([_api_row()])[WINDOW_START][0]

    assert row == {
        "profile_id": "555",
        "report_date": "2026-09-08",
        "campaign_id": "101",
        "impressions": 1200,
        "clicks": 34,
        "purchases_7d": 3,
        "purchases_14d": 4,
        "cost": 21.5,
        "sales_7d": 89.97,
        "sales_14d": 119.96,
        "currency_code": "USD",
        "budget_amount": None,
        "top_of_search_is": None,
    }


def test_the_budget_of_the_day_and_the_top_of_search_share_land_as_reported():
    row = _mapped([_api_row(campaignBudgetAmount=30.0, topOfSearchImpressionShare=6.48)])[WINDOW_START][0]

    # The share is a 0-100 percentage, the scale the real API answered in.
    assert (row["budget_amount"], row["top_of_search_is"]) == (30.0, 6.48)


def test_a_share_amazon_did_not_report_stays_unknown_instead_of_zero():
    row = _mapped([_api_row(campaignBudgetAmount=30.0, topOfSearchImpressionShare=None)])[WINDOW_START][0]

    assert row["top_of_search_is"] is None


def test_a_budget_or_share_below_zero_is_unknown_and_a_non_numeric_one_refuses_the_report():
    row = _mapped([_api_row(campaignBudgetAmount=-5.0, topOfSearchImpressionShare=-1.0)])[WINDOW_START][0]

    assert (row["budget_amount"], row["top_of_search_is"]) == (None, None)
    with pytest.raises(ReportRowsError, match="non-numeric"):
        _mapped([_api_row(topOfSearchImpressionShare="high")])
    with pytest.raises(ReportRowsError, match="impossible"):
        _mapped([_api_row(campaignBudgetAmount=float("inf"))])


def test_repeated_rows_weight_the_share_by_impressions_and_keep_the_known_budget():
    row = _mapped([
        _api_row(impressions=300, topOfSearchImpressionShare=10.0, campaignBudgetAmount=None),
        _api_row(impressions=100, topOfSearchImpressionShare=2.0, campaignBudgetAmount=25.0),
    ])[WINDOW_START][0]

    assert row["top_of_search_is"] == pytest.approx((10.0 * 300 + 2.0 * 100) / 400)
    assert row["budget_amount"] == 25.0
    assert row["impressions"] == 400


def test_the_report_asks_amazon_for_the_budget_and_the_share():
    from core.amazon_ads.campaign_rows import CAMPAIGN_REPORT_SPEC

    assert {"campaignBudgetAmount", "topOfSearchImpressionShare"} <= set(CAMPAIGN_REPORT_SPEC.columns)


def test_repeated_campaign_rows_in_one_day_are_summed():
    by_day = _mapped([
        _api_row(impressions=100, clicks=5, cost=1.25, purchases7d=1, sales7d=10.0),
        _api_row(impressions=50, clicks=2, cost=0.75, purchases7d=2, sales7d=20.0),
    ])

    row = by_day[WINDOW_START][0]
    assert (row["impressions"], row["clicks"], row["cost"]) == (150, 7, 2.0)
    assert (row["purchases_7d"], row["sales_7d"]) == (3, 30.0)


def test_numeric_campaign_ids_never_come_out_in_float_notation():
    row = _mapped([_api_row(campaign_id=218190823249654.0)])[WINDOW_START][0]

    assert row["campaign_id"] == "218190823249654"


def test_the_profile_currency_fills_in_when_the_report_omits_it():
    row = _mapped([_api_row(campaignBudgetCurrencyCode=None)], currency_code="mxn")[WINDOW_START][0]

    assert row["currency_code"] == "MXN"


def test_a_missing_metric_reads_as_zero_rather_than_failing():
    row = _mapped([_api_row(clicks=None, sales7d="")])[WINDOW_START][0]

    assert (row["clicks"], row["sales_7d"]) == (0, 0.0)


def test_a_row_dated_outside_the_window_is_refused():
    with pytest.raises(ReportRowsError, match="outside"):
        _mapped([_api_row(day="2026-09-20")])


def test_a_row_without_a_campaign_id_is_refused():
    with pytest.raises(ReportRowsError, match="no campaign id"):
        _mapped([_api_row(campaign_id=None)])


def test_a_row_without_a_usable_date_is_refused():
    with pytest.raises(ReportRowsError, match="no valid date"):
        _mapped([_api_row(day="")])


def test_the_adjustment_that_failed_shapermint_us_is_stored_as_a_day_without_activity(caplog):
    # The real row (spCampaigns DAILY, 30 Jul 2026): Amazon netted invalid traffic out of a day with nothing else.
    adjustment = _api_row(day="2026-09-09", campaign_id=228481306576207, impressions=-2, clicks=0, cost=0,
                          purchases7d=0, sales7d=0, purchases14d=0, sales14d=0, campaignBudgetAmount=5.0,
                          topOfSearchImpressionShare=26.09)

    with caplog.at_level("WARNING", logger="core.amazon_ads.campaign_rows"):
        by_day = _mapped([_api_row(), adjustment])

    (row,) = by_day[date(2026, 9, 9)]
    assert (row["campaign_id"], row["impressions"], row["cost"]) == ("228481306576207", 0, 0.0)
    assert by_day[WINDOW_START][0]["impressions"] == 1200
    assert "1 values below zero" in caplog.text and "impressions=-2" in caplog.text


@pytest.mark.parametrize("field", ["impressions", "clicks", "cost", "purchases7d", "sales7d", "purchases14d",
                                   "sales14d"])
def test_any_metric_below_zero_is_stored_as_zero_instead_of_failing_the_report(field):
    row = _mapped([_api_row(**{field: -1.5})])[WINDOW_START][0]

    column = {"purchases7d": "purchases_7d", "sales7d": "sales_7d", "purchases14d": "purchases_14d",
              "sales14d": "sales_14d"}.get(field, field)
    assert row[column] == 0


def test_a_negative_duplicate_row_cannot_push_the_merged_share_out_of_0_to_100():
    row = _mapped([
        _api_row(impressions=1000, topOfSearchImpressionShare=100.0),
        _api_row(impressions=-999, topOfSearchImpressionShare=0.0),
    ])[WINDOW_START][0]

    assert row["impressions"] == 1000
    assert row["top_of_search_is"] == pytest.approx(100.0)


def test_a_non_numeric_metric_is_refused():
    with pytest.raises(ReportRowsError, match="non-numeric"):
        _mapped([_api_row(impressions="many")])


def test_a_metric_that_is_not_a_finite_number_is_refused():
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ReportRowsError, match="impossible"):
            _mapped([_api_row(cost=value)])


def test_one_unusable_row_refuses_the_whole_window_before_any_day_is_written():
    with pytest.raises(ReportRowsError):
        _mapped([_api_row(day="2026-09-08"), _api_row(day="2026-09-09", cost=float("nan"))])


def test_a_window_that_ends_before_it_starts_is_refused():
    with pytest.raises(ReportRowsError, match="ends before it starts"):
        _mapped([], window_start=WINDOW_END, window_end=WINDOW_START)


def test_a_row_that_is_not_an_object_is_refused():
    with pytest.raises(ReportRowsError, match="not an object"):
        _mapped(["not a row"])

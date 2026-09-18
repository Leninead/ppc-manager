"""CampaignProvider over a fake PostgREST: the Campaign Manager export shape M6 and M8 read. No network."""
from __future__ import annotations

import csv
import io
import math
from datetime import date

import pytest
import requests

from core.amazon_ads.campaign_provider import CAMPAIGNS_RPC, FRAME_COLUMNS, CampaignProvider
from core.amazon_ads.report_provider import READ_TIMEOUT_SECONDS, ProfileOption, ReportReadError

RPC_HEADER = ["campaign_id", "name", "state", "targeting_type", "start_date", "budget_amount", "budget_type",
              "bidding_strategy", "portfolio_id", "portfolio_name", "impressions", "clicks", "cost",
              "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "currency_code"]
START, END = date(2026, 9, 8), date(2026, 9, 14)

# The literal column names bulk_campanas.py (M6) and analisis_funnel.py (M8) read from their input.
M6_COLUMNS = ("State", "Total cost", "Sales", "Purchases", "Impressions", "Clicks", "ACOS", "ROAS",
              "Campaign name", "Portfolio name", "Campaign start date", "Campaign bid strategy")
M8_COLUMNS = ("State", "Campaign name", "Type", "Portfolio name", "Campaign bid strategy",
              "Campaign budget amount", "Impressions", "Clicks", "CTR", "Total cost", "CPC", "Purchases",
              "Sales", "ACOS", "ROAS")


class _FakeRest:
    def __init__(self, *, csv_bytes=b"", fail_with=None):
        self._csv_bytes = csv_bytes
        self._fail_with = fail_with
        self.rpc_calls: list[tuple[str, dict, int]] = []

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.rpc_calls.append((name, args, timeout_s))
        if self._fail_with:
            raise self._fail_with
        return self._csv_bytes


def _option(**overrides) -> ProfileOption:
    row = {"profile_id": "279177258676903", "cliente": "Marca Demo", "country_code": "US", "currency_code": "USD",
           "account_type": "seller", "status": "active"}
    row.update(overrides)
    return ProfileOption.from_row(row)


def _rpc_row(**overrides) -> dict:
    row = {"campaign_id": "218190823249654", "name": "Demo - B0CYLMJJJC - SP - KW - EXACT - Brand",
           "state": "ENABLED", "targeting_type": "MANUAL", "start_date": "2026-03-21", "budget_amount": "15.0",
           "budget_type": "DAILY", "bidding_strategy": "MANUAL", "portfolio_id": "444",
           "portfolio_name": "Brand Portfolio", "impressions": "1200", "clicks": "40", "cost": "25.0",
           "purchases_7d": "4", "sales_7d": "100.0", "purchases_14d": "5", "sales_14d": "125.0",
           "currency_code": "USD"}
    row.update(overrides)
    return row


def _csv(*rows: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RPC_HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _frame(*rows: dict, **option_overrides):
    rest = _FakeRest(csv_bytes=_csv(*rows))
    return CampaignProvider(rest).campaigns(_option(**option_overrides), START, END).frame, rest


def test_the_frame_carries_every_column_m6_and_m8_read():
    frame, _ = _frame(_rpc_row())

    assert set(M6_COLUMNS) <= set(frame.columns)
    assert set(M8_COLUMNS) <= set(frame.columns)
    assert list(frame.columns) == list(FRAME_COLUMNS)


def test_acos_is_a_fraction_because_m6_multiplies_it_by_one_hundred():
    frame, _ = _frame(_rpc_row(cost="25.0", sales_7d="100.0"))

    assert frame.loc[0, "ACOS"] == pytest.approx(0.25)
    assert frame.loc[0, "ROAS"] == pytest.approx(4.0)


def test_ctr_and_cpc_come_out_of_the_same_totals():
    frame, _ = _frame(_rpc_row(impressions="1000", clicks="50", cost="25.0"))

    assert frame.loc[0, "CTR"] == pytest.approx(0.05)
    assert frame.loc[0, "CPC"] == pytest.approx(0.5)


def test_a_campaign_with_no_activity_is_a_row_of_zeros_with_undefined_ratios():
    frame, _ = _frame(_rpc_row(impressions="0", clicks="0", cost="0", purchases_7d="0", sales_7d="0"))

    row = frame.loc[0]
    assert (row["Impressions"], row["Clicks"], row["Total cost"], row["Sales"]) == (0, 0, 0.0, 0.0)
    assert all(math.isnan(row[column]) for column in ("CTR", "CPC", "ACOS", "ROAS"))


def test_sellers_read_seven_day_attribution_and_vendors_fourteen():
    seller, _ = _frame(_rpc_row())
    vendor, _ = _frame(_rpc_row(), account_type="vendor")

    assert (seller.loc[0, "Purchases"], seller.loc[0, "Sales"]) == (4, 100.0)
    assert (vendor.loc[0, "Purchases"], vendor.loc[0, "Sales"]) == (5, 125.0)


def test_archived_campaigns_stay_out_like_in_campaign_manager():
    frame, _ = _frame(_rpc_row(campaign_id="1", name="A"), _rpc_row(campaign_id="2", name="B", state="ARCHIVED"),
                      _rpc_row(campaign_id="3", name="C", state="paused"))

    assert list(frame["Campaign ID"]) == ["1", "3"]
    assert list(frame["State"]) == ["ENABLED", "PAUSED"]


def test_a_portfolio_without_a_name_is_still_named_instead_of_left_blank():
    frame, _ = _frame(_rpc_row(portfolio_id="555", portfolio_name=""),
                      _rpc_row(campaign_id="2", name="Z", portfolio_id="", portfolio_name=""))

    assert list(frame["Portfolio name"]) == ["Portfolio 555", ""]


def test_a_campaign_without_a_budget_has_an_empty_budget_not_zero():
    frame, _ = _frame(_rpc_row(budget_amount=""))

    assert math.isnan(frame.loc[0, "Campaign budget amount"])


def test_rows_come_in_a_fixed_order_whatever_order_the_database_answered():
    frame, _ = _frame(_rpc_row(campaign_id="9", name="Beta"), _rpc_row(campaign_id="2", name="Alpha"),
                      _rpc_row(campaign_id="1", name="Alpha"))

    assert list(frame["Campaign ID"]) == ["1", "2", "9"]


def test_campaign_ids_stay_text():
    frame, _ = _frame(_rpc_row(campaign_id="218190823249654"))

    assert frame.loc[0, "Campaign ID"] == "218190823249654"


def test_a_campaign_named_like_a_missing_value_stays_text():
    frame, _ = _frame(_rpc_row(name="NA"))

    assert frame.loc[0, "Campaign name"] == "NA"


def test_the_read_asks_the_database_for_exactly_the_range():
    _, rest = _frame(_rpc_row())

    assert rest.rpc_calls == [(CAMPAIGNS_RPC, {"p_profile_id": "279177258676903", "p_from": "2026-09-08",
                                               "p_to": "2026-09-14"}, READ_TIMEOUT_SECONDS)]


def test_the_source_carries_the_label_currency_and_window():
    rest = _FakeRest(csv_bytes=_csv(_rpc_row()))

    source = CampaignProvider(rest).campaigns(_option(), START, END)

    assert (source.label, source.currency_code, source.profile_id) == ("Marca Demo · US", "USD", "279177258676903")
    assert (source.window_start, source.window_end, source.attribution_days) == (START, END, 7)


def test_an_empty_answer_is_an_empty_frame_with_every_column():
    rest = _FakeRest(csv_bytes=b"")

    frame = CampaignProvider(rest).campaigns(_option(), START, END).frame

    assert frame.empty and list(frame.columns) == list(FRAME_COLUMNS)


def test_a_non_numeric_metric_is_a_read_error_not_a_zero():
    rest = _FakeRest(csv_bytes=_csv(_rpc_row(cost="lots")))

    with pytest.raises(ReportReadError):
        CampaignProvider(rest).campaigns(_option(), START, END)


def test_a_non_numeric_budget_is_a_read_error_not_an_empty_budget():
    rest = _FakeRest(csv_bytes=_csv(_rpc_row(budget_amount="fifteen")))

    with pytest.raises(ReportReadError):
        CampaignProvider(rest).campaigns(_option(), START, END)


def test_a_database_outage_is_a_read_error_the_page_can_show():
    rest = _FakeRest(fail_with=requests.ConnectionError("rest-gateway down"))

    with pytest.raises(ReportReadError):
        CampaignProvider(rest).campaigns(_option(), START, END)


def test_a_range_that_ends_before_it_starts_is_refused():
    with pytest.raises(ValueError):
        CampaignProvider(_FakeRest()).campaigns(_option(), END, START)

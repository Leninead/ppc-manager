"""ProductProvider over a fake PostgREST: SB / SD campaigns and idle targets for M6. No network."""
from __future__ import annotations

import csv
import io
import math
from datetime import date

import pandas as pd
import pytest
import requests

from core.amazon_ads.campaign_provider import FRAME_COLUMNS
from core.amazon_ads.product_provider import (
    GRADUATION_TARGETS_RPC,
    PRODUCT_CAMPAIGNS_RPC,
    PRODUCT_FRAME_COLUMNS,
    PURCHASES_CLICKS,
    SALES_CLICKS,
    ProductProvider,
    with_click_columns,
)
from core.amazon_ads.report_provider import READ_TIMEOUT_SECONDS, ReportReadError

START, END = date(2026, 9, 10), date(2026, 9, 16)
CAMPAIGN_HEADER = ["ad_product", "campaign_id", "name", "state", "start_date", "budget_amount", "budget_type",
                   "cost_type", "portfolio_id", "portfolio_name", "is_multi_ad_groups", "bid_strategy",
                   "metrics_known", "impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks",
                   "sales_clicks", "viewable_impressions", "currency_code"]
TARGET_HEADER = ["ad_product", "target_id", "campaign_id", "campaign_name", "ad_group_id", "target_kind",
                 "target_text", "match_type", "bid", "impressions"]


class _FakeRest:
    def __init__(self, answers=None, *, fail_with=None):
        self._answers = answers or {}
        self._fail_with = fail_with
        self.calls = []

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.calls.append((name, args, timeout_s))
        if self._fail_with:
            raise self._fail_with
        return self._answers.get(name, b"")


def _csv(header, *rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _campaign(**overrides) -> dict:
    row = {"ad_product": "SB", "campaign_id": "301", "name": "Demo SB - Video", "state": "ENABLED",
           "start_date": "2026-01-10", "budget_amount": "20", "budget_type": "DAILY", "cost_type": "CPC",
           "portfolio_id": "", "portfolio_name": "", "is_multi_ad_groups": "t",
           "bid_strategy": "MAXIMIZE_IMMEDIATE_SALES", "metrics_known": "t", "impressions": "1000",
           "clicks": "20", "cost": "10.0", "purchases": "4", "sales": "120.0", "purchases_clicks": "3",
           "sales_clicks": "90.0", "viewable_impressions": "800", "currency_code": "USD"}
    row.update(overrides)
    return row


def _target(**overrides) -> dict:
    row = {"ad_product": "SP", "target_id": "9001", "campaign_id": "11", "campaign_name": "Demo SP - Exact",
           "ad_group_id": "21", "target_kind": "keyword", "target_text": "demo keyword", "match_type": "EXACT",
           "bid": "0.85", "impressions": "0"}
    row.update(overrides)
    return row


def _campaigns(*rows):
    rest = _FakeRest({PRODUCT_CAMPAIGNS_RPC: _csv(CAMPAIGN_HEADER, *rows)})
    return ProductProvider(rest).campaigns("p-1", START, END), rest


def test_sb_and_sd_campaigns_come_in_the_exports_columns_plus_the_click_only_ones():
    result, rest = _campaigns(_campaign(), _campaign(ad_product="SD", campaign_id="401", name="Demo SD - Views",
                                                     cost_type="VCPM"))

    assert list(result.frame.columns) == list(PRODUCT_FRAME_COLUMNS)
    assert list(result.frame["Type"]) == ["Sponsored Brands", "Sponsored Display"]
    assert rest.calls == [(PRODUCT_CAMPAIGNS_RPC, {"p_profile_id": "p-1", "p_from": "2026-09-10",
                                                   "p_to": "2026-09-16"}, READ_TIMEOUT_SECONDS)]


def test_purchases_and_sales_are_campaign_managers_and_the_click_only_ones_go_apart():
    result, _ = _campaigns(_campaign(purchases="4", sales="120.0", purchases_clicks="3", sales_clicks="90.0"))

    row = result.frame.iloc[0]
    assert (row["Purchases"], row["Sales"]) == (4, 120.0)
    assert (row[PURCHASES_CLICKS], row[SALES_CLICKS]) == (3, 90.0)
    assert row["ACOS"] == pytest.approx(10.0 / 120.0)


def test_an_sb_campaign_the_reports_leave_out_has_unknown_metrics_not_zeros():
    # "f" is how PostgREST's CSV writes a false boolean.
    result, _ = _campaigns(_campaign(campaign_id="302", is_multi_ad_groups="f", metrics_known="f",
                                     impressions="0", clicks="0", cost="0", sales="0"))

    row = result.frame.iloc[0]
    assert result.without_metrics == frozenset({"302"})
    assert pd.isna(row["Impressions"]) and pd.isna(row["Clicks"]) and math.isnan(row["Total cost"])
    assert math.isnan(row["Sales"])


def test_an_old_format_sb_campaign_has_its_metrics_once_the_v2_history_loaded():
    result, _ = _campaigns(_campaign(campaign_id="302", is_multi_ad_groups="f", metrics_known="t", cost="12.5"))

    assert result.without_metrics == frozenset()
    assert result.frame.iloc[0]["Total cost"] == 12.5


def test_an_sd_campaign_is_never_marked_as_left_out():
    result, _ = _campaigns(_campaign(ad_product="SD", campaign_id="401", is_multi_ad_groups=""))

    assert result.without_metrics == frozenset()
    assert result.frame.iloc[0]["Impressions"] == 1000


@pytest.mark.parametrize("ad_product, code, label", [
    ("SB", "MANUAL", "Custom bid adjustments"),
    ("SB", "MAXIMIZE_IMMEDIATE_SALES", "Automated bidding"),
    ("SB", "MAXIMIZE_NEW_TO_BRAND_CUSTOMERS", "Automated bidding - new-to-brand customers"),
    ("SD", "conversions", "Optimize for conversions"),
    ("SD", "clicks,reach", "Optimize for page visits / Optimize for reach"),
    # A code Amazon adds later shows as it came, never as empty.
    ("SD", "someNewGoal", "someNewGoal"),
    ("SB", "", ""),
])
def test_the_bid_strategy_reads_as_campaign_manager_names_it(ad_product, code, label):
    result, _ = _campaigns(_campaign(ad_product=ad_product, bid_strategy=code))

    assert result.frame.iloc[0]["Campaign bid strategy"] == label


def test_rows_come_by_product_then_name():
    result, _ = _campaigns(_campaign(ad_product="SD", campaign_id="9", name="Alpha"),
                           _campaign(campaign_id="8", name="Zeta"), _campaign(campaign_id="7", name="Beta"))

    assert list(result.frame["Campaign ID"]) == ["7", "8", "9"]


def test_a_missing_function_means_the_migration_is_pending_not_an_error():
    response = requests.Response()
    response.status_code = 404
    response._content = b'{"code":"PGRST202","message":"Could not find the function"}'
    rest = _FakeRest(fail_with=requests.HTTPError(response=response))

    assert ProductProvider(rest).campaigns("p-1", START, END) is None
    assert ProductProvider(rest).idle_targets("p-1", START, END) is None


def test_any_other_failure_is_a_read_error():
    rest = _FakeRest(fail_with=requests.ConnectionError("rest-gateway down"))

    with pytest.raises(ReportReadError):
        ProductProvider(rest).campaigns("p-1", START, END)


def test_a_non_numeric_metric_is_a_read_error():
    with pytest.raises(ReportReadError):
        _campaigns(_campaign(cost="lots"))


def test_idle_targets_are_the_ones_without_impressions_out_of_every_target_looked_at():
    rest = _FakeRest({GRADUATION_TARGETS_RPC: _csv(
        TARGET_HEADER, _target(), _target(target_id="9003", target_text="busy keyword", impressions="120"),
        _target(ad_product="SD", target_id="9002", target_kind="audience", target_text='views=(lookback=30)',
                match_type="", bid=""))})

    idle = ProductProvider(rest).idle_targets("p-1", START, END)

    assert idle.considered == {"SD": 1, "SP": 2}
    assert list(idle.frame["Producto"]) == ["SP", "SD"]
    assert list(idle.frame["Tipo de target"]) == ["Keyword", "Audiencia"]
    assert idle.frame.iloc[0]["Bid"] == 0.85 and math.isnan(idle.frame.iloc[1]["Bid"])


def test_targets_that_all_had_impressions_are_counted_with_none_idle():
    rest = _FakeRest({GRADUATION_TARGETS_RPC: _csv(TARGET_HEADER, _target(impressions="7"))})

    idle = ProductProvider(rest).idle_targets("p-1", START, END)

    assert idle.frame.empty and idle.considered == {"SP": 1}


def test_no_target_to_look_at_is_an_empty_frame_with_nothing_considered():
    idle = ProductProvider(_FakeRest({GRADUATION_TARGETS_RPC: b""})).idle_targets("p-1", START, END)

    assert idle.frame.empty and idle.considered == {}


def test_the_sp_frame_gets_its_own_numbers_as_the_click_only_columns():
    sp = pd.DataFrame([{column: None for column in FRAME_COLUMNS} | {"Purchases": 5, "Sales": 99.5}])

    frame = with_click_columns(sp)

    assert (frame.iloc[0][PURCHASES_CLICKS], frame.iloc[0][SALES_CLICKS]) == (5, 99.5)
    assert list(frame.columns) == list(PRODUCT_FRAME_COLUMNS)

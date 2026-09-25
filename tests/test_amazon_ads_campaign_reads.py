"""The reads migration 019 adds: the campaign catalog, the series by campaign id, new-to-brand for SB and SD, and
the SB and SD keywords and targets with each target's top-of-search share."""
from __future__ import annotations

import csv
import io
import math
from datetime import date

import pandas as pd
import pytest
import requests

from core.amazon_ads import campaign_totals
from core.amazon_ads.campaign_catalog import CATALOG_COLUMNS, campaign_catalog
from core.amazon_ads.product_provider import NewToBrand, ProductProvider
from core.amazon_ads.report_provider import ProfileOption, ReportProvider
from core.amazon_ads.structure_provider import SB_SD_TARGET_COLUMNS, StructureProvider

PROFILE = ProfileOption.from_row({"profile_id": "111", "account_type": "seller", "currency_code": "USD",
                                  "data_from": "2026-08-01", "data_through": "2026-09-16"})
START, END = date(2026, 9, 1), date(2026, 9, 7)


def _csv(header, rows) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _missing_function() -> requests.HTTPError:
    response = requests.Response()
    response.status_code = 404
    response._content = b'{"code": "PGRST202"}'
    return requests.HTTPError(response=response)


class _FakeRest:
    def __init__(self, csv_answers=None, json_answers=None, missing=()):
        self.csv_answers = csv_answers or {}
        self.json_answers = json_answers or {}
        self.missing = set(missing)
        self.calls: list[tuple[str, dict]] = []

    def rpc_csv(self, name, args, **_):
        self.calls.append((name, args))
        if name in self.missing:
            raise _missing_function()
        return self.csv_answers[name]

    def rpc(self, name, args, **_):
        self.calls.append((name, args))
        if name in self.missing:
            raise _missing_function()
        return self.json_answers[name]


CATALOG_HEADER = ["ad_product", "campaign_id", "name", "state", "portfolio_id", "portfolio_name", "budget_amount",
                  "budget_type"]


def test_the_catalog_names_every_listed_campaign_with_its_state_portfolio_and_daily_budget():
    rest = _FakeRest({"campaign_catalog": _csv(CATALOG_HEADER, [
        {"ad_product": "SP", "campaign_id": "1", "name": " Demo - Exact ", "state": "enabled", "portfolio_id": "9",
         "portfolio_name": "", "budget_amount": "20", "budget_type": "DAILY"},
        {"ad_product": "SB", "campaign_id": "2", "name": "Video", "state": "PAUSED", "portfolio_id": "",
         "portfolio_name": "", "budget_amount": "500", "budget_type": "LIFETIME"}])})

    catalog = campaign_catalog(rest, "111")

    assert list(catalog.columns) == list(CATALOG_COLUMNS)
    assert catalog.to_dict("records")[0] == {"product": "SP", "campaign_id": "1", "campaign": "Demo - Exact",
                                             "state": "ENABLED", "portfolio": "Portfolio 9", "daily_budget": 20.0}
    # A lifetime budget is no daily budget.
    assert math.isnan(catalog.to_dict("records")[1]["daily_budget"])


def test_the_catalog_is_none_while_the_database_lacks_migration_019():
    assert campaign_catalog(_FakeRest(missing={"campaign_catalog"}), "111") is None


def _day(campaign_id: str, product: str = "SP", *, ntb=None, cost=10.0) -> dict:
    sp = product == "SP"
    return {"report_date": "2026-09-02", "ad_product": product, "campaign_id": campaign_id, "impressions": 100,
            "clicks": 5, "cost": cost, "purchases_7d": 2 if sp else 0, "sales_7d": 40.0 if sp else 0,
            "purchases_14d": 2 if sp else 0, "sales_14d": 40.0 if sp else 0, "purchases": 0 if sp else 3,
            "sales": 0 if sp else 60.0, "purchases_clicks": 0 if sp else 1, "sales_clicks": 0 if sp else 20.0,
            "new_to_brand_purchases": None if ntb is None else ntb[0],
            "new_to_brand_sales": None if ntb is None else ntb[1], "currency_code": "USD"}


def test_a_series_by_campaign_reads_the_campaigns_asked_for_by_id_one_row_each():
    """Five campaigns sharing a prefix were read as one: now each is read by its id."""
    rest = _FakeRest(json_answers={"campaign_daily_totals_by_campaign": [_day("1"), _day("2", "SB", ntb=(1, 30.0))]})

    rows = campaign_totals.daily_totals_by_campaign(rest, PROFILE, START, END, ("1", "2"))

    assert rest.calls[0][1]["p_campaign_ids"] == ["1", "2"]
    assert rows[["campaign_id", "product", "spend", "sales", "orders"]].to_dict("records") == [
        {"campaign_id": "1", "product": "SP", "spend": 10.0, "sales": 40.0, "orders": 2},
        {"campaign_id": "2", "product": "SB", "spend": 10.0, "sales": 60.0, "orders": 3}]
    # SP has no new-to-brand; SB carries its own.
    assert math.isnan(rows.iloc[0]["ntb_orders"]) and rows.iloc[1]["ntb_orders"] == 1


def test_a_series_by_campaign_without_ids_reads_nothing_and_without_019_is_none():
    assert campaign_totals.daily_totals_by_campaign(_FakeRest(), PROFILE, START, END, ()).empty
    missing = _FakeRest(missing={"campaign_daily_totals_by_campaign"})
    assert campaign_totals.daily_totals_by_campaign(missing, PROFILE, START, END, ("1",)) is None


def test_the_search_terms_are_read_by_campaign_id_too():
    rest = _FakeRest(json_answers={"ads_daily_totals_by_campaign": [
        {"report_date": "2026-09-02", "campaign_id": "1", "impressions": 40, "clicks": 5, "cost": 10.0,
         "purchases_7d": 2, "sales_7d": 40.0, "purchases_14d": 3, "sales_14d": 50.0, "currency_code": "USD"}]})

    rows = ReportProvider(rest).daily_totals_by_campaign(PROFILE, START, END, ("1",))

    assert rows.to_dict("records") == [{"day": date(2026, 9, 2), "campaign_id": "1", "impressions": 40, "clicks": 5,
                                        "spend": 10.0, "sales": 40.0, "orders": 2}]


WINDOW_HEADER = ["ad_product", "campaign_id", "campaign_name", "portfolio_id", "portfolio_name", "impressions", "clicks",
                 "cost", "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "purchases", "sales",
                 "purchases_clicks", "sales_clicks", "currency_code", "new_to_brand_purchases", "new_to_brand_sales"]


def test_window_totals_keep_each_campaign_id_and_its_new_to_brand_figures():
    rows = [{key: value for key, value in _day("2", "SB", ntb=(2, 50.0)).items() if key in WINDOW_HEADER}
            | {"campaign_name": "Video", "portfolio_id": "", "portfolio_name": ""},
            {key: value for key, value in _day("3", "SD").items() if key in WINDOW_HEADER}
            | {"campaign_name": "Display", "portfolio_id": "", "portfolio_name": "", "new_to_brand_purchases": "",
               "new_to_brand_sales": ""}]

    frame = campaign_totals.window_totals(_FakeRest({"campaign_window_totals": _csv(WINDOW_HEADER, rows)}), PROFILE,
                                          START, END)

    assert list(frame["campaign_id"]) == ["2", "3"]
    assert (frame.iloc[0]["ntb_orders"], frame.iloc[0]["ntb_sales"]) == (2, 50.0)
    # SD rows stored before 019 never measured new-to-brand: unknown, never zero.
    assert math.isnan(frame.iloc[1]["ntb_orders"])


def test_a_campaign_whose_window_is_all_zero_is_no_activity():
    """«73 campañas con actividad» counted 24 that had no impression, click or spend in the month."""
    served = {key: value for key, value in _day("2", "SB").items() if key in WINDOW_HEADER}
    idle = served | {"campaign_id": "3", "impressions": 0, "clicks": 0, "cost": 0, "purchases": 0, "sales": 0,
                     "purchases_clicks": 0, "sales_clicks": 0}
    rows = [row | {"campaign_name": f"Campaña {row['campaign_id']}", "portfolio_id": "", "portfolio_name": ""}
            for row in (served, idle)]

    frame = campaign_totals.window_totals(_FakeRest({"campaign_window_totals": _csv(WINDOW_HEADER, rows)}), PROFILE,
                                          START, END)

    assert list(frame["campaign_id"]) == ["2"]


def test_a_series_of_one_brand_or_display_product_carries_each_day_new_to_brand():
    days = [{**_day("2", "SB", ntb=(1, 30.0)), "report_date": "2026-09-01", "campaign_names": None},
            {**_day("2", "SB"), "report_date": "2026-09-02", "campaign_names": None}]
    rest = _FakeRest(json_answers={"campaign_daily_totals": days})

    series = campaign_totals.daily_totals(rest, PROFILE, date(2026, 9, 1), date(2026, 9, 3), product="SB")

    assert series.new_to_brand == (NewToBrand(1, 30.0), None, NewToBrand(0, 0.0))
    assert campaign_totals.daily_totals(rest, PROFILE, date(2026, 9, 1), date(2026, 9, 3)).new_to_brand == ()
    assert campaign_totals.sum_new_to_brand(series.new_to_brand) is None
    assert campaign_totals.sum_new_to_brand([NewToBrand(1, 30.0), NewToBrand(2, 5.5)]) == NewToBrand(3, 35.5)


PRODUCT_HEADER = ["ad_product", "campaign_id", "name", "state", "start_date", "budget_amount", "budget_type",
                  "cost_type", "portfolio_id", "portfolio_name", "is_multi_ad_groups", "bid_strategy", "metrics_known",
                  "impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks", "sales_clicks",
                  "viewable_impressions", "currency_code", "new_to_brand_purchases", "new_to_brand_sales"]


def _product_campaign(campaign_id: str, product: str, ntb: tuple[str, str]) -> dict:
    return {"ad_product": product, "campaign_id": campaign_id, "name": f"C{campaign_id}", "state": "ENABLED",
            "start_date": "", "budget_amount": "20", "budget_type": "DAILY", "cost_type": "CPC", "portfolio_id": "",
            "portfolio_name": "", "is_multi_ad_groups": "t", "bid_strategy": "", "metrics_known": "t",
            "impressions": "100", "clicks": "5", "cost": "10", "purchases": "3", "sales": "60",
            "purchases_clicks": "1", "sales_clicks": "20", "viewable_impressions": "0", "currency_code": "USD",
            "new_to_brand_purchases": ntb[0], "new_to_brand_sales": ntb[1]}


def test_each_sb_and_sd_campaign_says_its_new_to_brand_figures_or_that_they_are_unknown():
    rest = _FakeRest({"product_campaigns_between": _csv(PRODUCT_HEADER, [
        _product_campaign("7", "SB", ("2", "45.5")), _product_campaign("8", "SD", ("", ""))])})

    products = ProductProvider(rest).campaigns("111", START, END)

    assert products.new_to_brand == {"7": NewToBrand(2, 45.5), "8": None}


TARGET_ROW = {"entity": "keyword", "campaign_id": "7", "ad_group_id": "70", "entity_id": "700",
              "campaign_name": "Brand SB", "campaign_state": "ENABLED", "cost_type": "CPC", "ad_group_name": "AG",
              "state": "ENABLED",
              "target_kind": "keyword", "target_text": "dermaglos cream", "match_type": "EXACT", "default_bid": "0.8",
              "own_bid": "", "bid": "0.8", "impressions": "120", "clicks": "6", "cost": "4.5", "purchases": "2",
              "sales": "40", "purchases_clicks": "1", "sales_clicks": "20", "top_of_search_share": "",
              "metrics_known": "t", "currency_code": "USD", "listed_at": "2026-09-16T06:00:00+00:00"}


def test_the_sb_and_sd_keywords_and_targets_come_typed_with_their_campaign_state():
    rest = _FakeRest({"sb_sd_targets_between": _csv(SB_SD_TARGET_COLUMNS, [TARGET_ROW])})

    rows = StructureProvider(rest).sb_sd_targets(PROFILE, START, END, "SB")

    assert rest.calls[0][1]["p_ad_product"] == "SB"
    record = rows.to_dict("records")[0]
    assert (record["campaign_state"], record["bid"], record["cost"], record["purchases"]) == ("ENABLED", 0.8, 4.5, 2)
    assert math.isnan(record["own_bid"]) and math.isnan(record["top_of_search_share"])
    with pytest.raises(ValueError, match="SB or SD"):
        StructureProvider(rest).sb_sd_targets(PROFILE, START, END, "SP")


def test_rows_without_reports_in_the_window_have_unknown_metrics():
    unknown = {**TARGET_ROW, "metrics_known": "f"}
    rows = StructureProvider(_FakeRest({"sb_sd_targets_between": _csv(SB_SD_TARGET_COLUMNS, [unknown])})).sb_sd_targets(
        PROFILE, START, END, "SD")

    assert pd.isna(rows.iloc[0]["cost"]) and not rows.iloc[0]["metrics_known"]


def test_each_target_says_its_top_of_search_share_when_amazon_gave_one():
    rest = _FakeRest({"target_top_of_search_between": _csv(["target_id", "top_of_search_share"], [
        {"target_id": "700", "top_of_search_share": "12.5"}, {"target_id": "701", "top_of_search_share": ""}])})

    assert StructureProvider(rest).target_top_of_search(PROFILE, START, END, "SP") == {"700": 12.5}
    assert StructureProvider(_FakeRest(missing={"target_top_of_search_between"})).target_top_of_search(
        PROFILE, START, END, "SP") is None

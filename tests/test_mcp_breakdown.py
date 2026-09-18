"""breakdown: a total split by campaign, portfolio, match type or search term, in one call."""
from __future__ import annotations

import csv
import io

import pytest

from services.mcp_server.tools import amazon_ads

PROFILE = {
    "profile_id": "1111222233334444", "account_id": 7, "cliente": "Marca Demo", "account_name": "Demo LLC",
    "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "", "status": "active",
    "data_from": "2026-08-01", "data_through": "2026-09-16", "refreshed_on": "2026-09-17",
    "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": "",
}
HEADER = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting", "search_term",
          "campaign_name", "campaign_status", "ad_group_name", "keyword_text", "ad_keyword_status", "portfolio_id",
          "portfolio_name", "impressions", "clicks", "cost", "purchases_7d", "sales_7d", "units_7d",
          "purchases_14d", "sales_14d", "units_14d", "currency_code"]


def _row(term: str, campaign: str, *, cost: float, clicks: int, sales: float = 0.0, orders: int = 0,
         match_type: str = "EXACT", keyword_type: str = "EXACT", portfolio: str = "Marca", impressions: int = 100,
         orders_14d: int | None = None) -> dict:
    return {"campaign_id": campaign, "ad_group_id": "ag", "keyword_type": keyword_type, "keyword_id": term,
            "match_type": match_type, "targeting": term, "search_term": term, "campaign_name": campaign,
            "campaign_status": "ENABLED", "ad_group_name": "ag", "keyword_text": term, "ad_keyword_status": "ENABLED",
            "portfolio_id": "1" if portfolio else "", "portfolio_name": portfolio, "impressions": impressions,
            "clicks": clicks, "cost": cost, "purchases_7d": orders, "sales_7d": sales, "units_7d": orders,
            "purchases_14d": orders if orders_14d is None else orders_14d, "sales_14d": sales, "units_14d": orders,
            "currency_code": "USD"}


class _FakeRest:
    def __init__(self, rows, profile=None):
        self._rows = rows
        self._profile = profile or PROFILE
        self.rpc_calls: list[dict] = []

    def select(self, table, params):
        return [self._profile]

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.rpc_calls.append(args)
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(self._rows)
        return out.getvalue().encode("utf-8")


ROWS = [
    _row("zapatilla", "Camp A", cost=30.0, clicks=10, sales=120.0, orders=4),
    _row("zapatilla roja", "Camp A", cost=10.0, clicks=30, match_type="BROAD", keyword_type="BROAD"),
    _row("zapatilla", "Camp B", cost=5.0, clicks=5, sales=20.0, orders=1, match_type="", keyword_type="",
         portfolio=""),
    _row("b0asin", "Camp C", cost=15.0, clicks=2, match_type="TARGETING_EXPRESSION_PREDEFINED",
         keyword_type="TARGETING_EXPRESSION_PREDEFINED", portfolio="Otro"),
]


def _breakdown(**kwargs):
    return amazon_ads.breakdown(_FakeRest(kwargs.pop("rows", ROWS)), profile_id="1111222233334444", **kwargs)


def test_a_campaign_breakdown_sums_every_search_term_of_each_campaign_largest_spend_first():
    payload = _breakdown(by="campaign")

    assert [row["group"] for row in payload["rows"]] == ["Camp A", "Camp C", "Camp B"]
    assert payload["rows"][0] == {"group": "Camp A", "spend": 40.0, "sales": 120.0, "orders": 4, "clicks": 40,
                                  "impressions": 200, "acos": 33.3, "cvr": 10.0}


def test_the_totals_cover_every_group_so_a_share_of_the_whole_can_be_computed():
    payload = _breakdown(by="campaign", limit=1)

    assert len(payload["rows"]) == 1 and payload["total"] == 3 and "note" in payload
    assert payload["totals"] == {"spend": 60.0, "sales": 140.0, "orders": 5, "clicks": 47, "impressions": 400,
                                 "acos": 42.9, "cvr": 10.64}


def test_a_match_type_breakdown_tells_auto_from_the_keyword_types_in_words_the_am_reads():
    groups = {row["group"]: row["spend"] for row in _breakdown(by="match_type")["rows"]}

    assert groups == {"Exact": 30.0, "Broad": 10.0, "Automática": 15.0, "Sin tipo": 5.0}


def test_a_portfolio_breakdown_names_the_spend_outside_any_portfolio():
    groups = {row["group"]: row["spend"] for row in _breakdown(by="portfolio")["rows"]}

    assert groups == {"Marca": 40.0, "Otro": 15.0, "Sin portfolio": 5.0}


def test_a_search_term_breakdown_adds_up_the_same_term_across_campaigns():
    rows = _breakdown(by="search_term")["rows"]

    assert rows[0] == {"group": "zapatilla", "spend": 35.0, "sales": 140.0, "orders": 5, "clicks": 15,
                       "impressions": 200, "acos": 25.0, "cvr": 33.33}


def test_any_metric_can_rank_the_groups():
    assert [row["group"] for row in _breakdown(by="search_term", sort_by="clicks")["rows"]] == [
        "zapatilla roja", "zapatilla", "b0asin"]


def test_ranking_by_acos_leaves_the_groups_that_never_sold_last():
    """Without sales there is no ACoS: those groups go last with a null, never with an invented number."""
    ranked = [row["group"] for row in _breakdown(by="campaign", sort_by="acos")["rows"]]

    assert ranked == ["Camp A", "Camp B", "Camp C"]


def test_a_vendor_account_reads_fourteen_day_orders():
    rows = [_row("x", "Camp A", cost=10.0, clicks=10, sales=50.0, orders=1, orders_14d=3)]
    payload = amazon_ads.breakdown(_FakeRest(rows, profile={**PROFILE, "account_type": "vendor"}),
                                   profile_id="1111222233334444", by="campaign")

    assert payload["rows"][0]["orders"] == 3 and payload["attribution_days"] == 14


def test_a_window_without_clicks_says_so_instead_of_answering_an_empty_split():
    payload = _breakdown(by="campaign", rows=[])

    assert payload["rows"] == [] and payload["totals"] is None and "note" in payload


def test_the_breakdown_says_it_is_sponsored_products_and_which_window_it_covers():
    payload = _breakdown(by="campaign", days=7)

    assert "Sponsored Products" in payload["source"]
    assert payload["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}


def test_an_unknown_dimension_is_refused_with_the_ones_that_exist():
    with pytest.raises(ValueError, match="campaign, portfolio, match_type, search_term"):
        _breakdown(by="ad_group")


def test_an_unknown_ranking_metric_is_refused_too():
    with pytest.raises(ValueError, match="spend"):
        _breakdown(by="campaign", sort_by="margen")

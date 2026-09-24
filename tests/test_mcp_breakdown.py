"""breakdown: a total split by campaign, portfolio, product, match type or search term, in one call."""
from __future__ import annotations

import csv
import io

from pathlib import Path

import pytest

from services.mcp_server import server
from services.mcp_server.tools import amazon_ads

PROFILE = {
    "profile_id": "1111222233334444", "account_id": 7, "cliente": "Marca Demo", "account_name": "Demo LLC",
    "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "", "status": "active",
    "data_from": "2026-08-01", "data_through": "2026-09-16", "refreshed_on": "2026-09-17",
    "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": "",
}
CAMPAIGN_JOB = {"id": 441, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns", "trigger": "scheduled_daily",
                "external_account_id": "1111222233334444", "status": "completed", "window_start": "2026-08-01",
                "window_end": "2026-09-16", "local_day": "2026-09-17", "finished_at": "2026-09-17T11:05:00+00:00",
                "created_at": "2026-09-17T10:43:00+00:00"}
TERM_HEADER = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting", "search_term",
               "campaign_name", "campaign_status", "ad_group_name", "keyword_text", "ad_keyword_status", "portfolio_id",
               "portfolio_name", "impressions", "clicks", "cost", "purchases_7d", "sales_7d", "units_7d",
               "purchases_14d", "sales_14d", "units_14d", "currency_code"]
CAMPAIGN_HEADER = ["ad_product", "campaign_id", "campaign_name", "portfolio_id", "portfolio_name", "impressions",
                   "clicks", "cost", "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "purchases", "sales",
                   "purchases_clicks", "sales_clicks", "currency_code"]


def _term(term: str, campaign: str, *, cost: float, clicks: int, sales: float = 0.0, orders: int = 0,
          match_type: str = "EXACT", keyword_type: str = "EXACT", portfolio: str = "Marca",
          impressions: int = 100, ad_group: str = "ag") -> dict:
    return {"campaign_id": campaign, "ad_group_id": ad_group, "keyword_type": keyword_type, "keyword_id": term,
            "match_type": match_type, "targeting": term, "search_term": term, "campaign_name": campaign,
            "campaign_status": "ENABLED", "ad_group_name": "ag", "keyword_text": term, "ad_keyword_status": "ENABLED",
            "portfolio_id": "1" if portfolio else "", "portfolio_name": portfolio, "impressions": impressions,
            "clicks": clicks, "cost": cost, "purchases_7d": orders, "sales_7d": sales, "units_7d": orders,
            "purchases_14d": orders, "sales_14d": sales, "units_14d": orders, "currency_code": "USD"}


def _campaign(name: str, *, cost: float, clicks: int, sales: float = 0.0, orders: int = 0, product: str = "SP",
              portfolio: str = "Marca", impressions: int = 100, orders_14d: int | None = None,
              sales_clicks: float | None = None, orders_clicks: int | None = None) -> dict:
    sp = product == "SP"
    return {"ad_product": product, "campaign_id": name, "campaign_name": name, "portfolio_id": "1" if portfolio else "",
            "portfolio_name": portfolio, "impressions": impressions, "clicks": clicks, "cost": cost,
            "purchases_7d": orders if sp else 0, "sales_7d": sales if sp else 0,
            "purchases_14d": (orders if orders_14d is None else orders_14d) if sp else 0,
            "sales_14d": sales if sp else 0, "purchases": 0 if sp else orders, "sales": 0 if sp else sales,
            "purchases_clicks": 0 if sp else (orders if orders_clicks is None else orders_clicks),
            "sales_clicks": 0 if sp else (sales if sales_clicks is None else sales_clicks), "currency_code": "USD"}


def _csv(header, rows) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


class _FakeRest:
    def __init__(self, terms=(), campaigns=(), profile=None, product_ads=()):
        self._terms = list(terms)
        self._campaigns = list(campaigns)
        self._profile = profile or PROFILE
        self._product_ads = list(product_ads)
        self.rpc_calls: list[tuple[str, dict]] = []

    def select(self, table, params):
        if table == "integration_sync_jobs":
            return [dict(CAMPAIGN_JOB)] if params.get("job_kind") == "eq.sp_campaigns" else []
        if table == "ads_product_ad":
            return list(self._product_ads)
        return [self._profile]

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.rpc_calls.append((name, args))
        if name == "campaign_window_totals":
            return _csv(CAMPAIGN_HEADER, self._campaigns)
        if name == "product_campaigns_between":
            return b""
        assert name == "search_terms_between"
        return _csv(TERM_HEADER, self._terms)


TERMS = [
    _term("zapatilla", "Camp A", cost=30.0, clicks=10, sales=120.0, orders=4),
    _term("zapatilla roja", "Camp A", cost=10.0, clicks=30, match_type="BROAD", keyword_type="BROAD"),
    _term("zapatilla", "Camp B", cost=5.0, clicks=5, sales=20.0, orders=1, match_type="", keyword_type="",
          portfolio=""),
    _term("b0asin", "Camp C", cost=15.0, clicks=2, match_type="TARGETING_EXPRESSION_PREDEFINED",
          keyword_type="TARGETING_EXPRESSION_PREDEFINED", portfolio="Otro"),
]
CAMPAIGNS = [
    _campaign("Camp A", cost=40.0, clicks=40, sales=120.0, orders=4, impressions=200),
    _campaign("Camp B", cost=5.0, clicks=5, sales=20.0, orders=1, portfolio=""),
    _campaign("Camp C", cost=15.0, clicks=2, portfolio="Otro"),
]


def _breakdown(**kwargs):
    rest = _FakeRest(kwargs.pop("terms", TERMS), kwargs.pop("campaigns", CAMPAIGNS), kwargs.pop("profile", None),
                     kwargs.pop("product_ads", ()))
    return amazon_ads.breakdown(rest, profile_id="1111222233334444", **kwargs)


def test_the_leaders_of_each_metric_cover_every_group_not_only_the_page():
    """The chat said Exact had «the lowest ACoS after Broad»: Exact was the lowest. The comparison comes done."""
    payload = _breakdown(by="campaign", limit=1)

    assert payload["showing"] == 1
    assert payload["leaders"]["most_spend"] == {"group": "Camp A", "spend": 40.0}
    assert payload["leaders"]["lowest_acos"] == {"group": "Camp B", "acos": 25.0}
    assert payload["leaders"]["highest_acos"]["group"] == "Camp A"
    assert payload["leaders"]["groups_spending_without_sales"] == 1


def test_a_list_by_a_criterion_comes_from_the_filters_complete_and_counted():
    """Listing «the terms with 4+ orders under 30%» by eye, the chat dropped one of the rows that met it."""
    payload = _breakdown(by="campaign", min_orders=1, max_acos=30)

    assert [row["group"] for row in payload["rows"]] == ["Camp B"]
    assert payload["total"] == 1
    assert payload["filters"] == {"min_orders": 1, "max_acos": 30}
    assert payload["totals"]["spend"] == 60.0

    unsold = _breakdown(by="campaign", without_sales=True)
    assert [row["group"] for row in unsold["rows"]] == ["Camp C"]


ASIN_TERMS = [
    _term("vitamin cream", "DG - Exact", cost=40.0, clicks=20, sales=160.0, orders=4, ad_group="AG1"),
    _term("night cream", "DG - Exact", cost=10.0, clicks=10, ad_group="AG1"),
    _term("lotion", "DG - Variants", cost=25.0, clicks=5, ad_group="AG2"),
    _term("body lotion", "DG - B0NAMED001 - Broad", cost=15.0, clicks=6, sales=30.0, orders=1, ad_group="AG9"),
    _term("cream", "DG - Auto", cost=10.0, clicks=4, ad_group="AG8"),
]
PRODUCT_ADS = [{"ad_group_id": "AG1", "asin": "B0HERO00001"},
               {"ad_group_id": "AG2", "asin": "B0VARIANT01"}, {"ad_group_id": "AG2", "asin": "B0VARIANT02"}]


def test_an_asin_breakdown_attributes_each_term_to_its_ad_groups_asin_and_keeps_the_rest_apart():
    payload = _breakdown(by="asin", terms=ASIN_TERMS, product_ads=PRODUCT_ADS)

    spend = {row["group"]: row["spend"] for row in payload["rows"]}
    assert spend == {"B0HERO00001": 50.0, "Varios ASINs en el ad group": 25.0, "B0NAMED001": 15.0,
                     "Sin ASIN": 10.0}
    assert payload["totals"]["spend"] == 100.0
    assert "producto anunciado" in payload["asin_note"]


def test_a_family_asin_in_the_campaign_name_takes_its_several_asin_ad_group_and_the_groups_still_add_up():
    terms = ASIN_TERMS + [_term("shaper shorts", "DG - B0FAMILY01 - Broad", cost=20.0, clicks=8, ad_group="AG2")]

    payload = _breakdown(by="asin", terms=terms, product_ads=PRODUCT_ADS)

    spend = {row["group"]: row["spend"] for row in payload["rows"]}
    assert spend["B0FAMILY01"] == 20.0 and spend["Varios ASINs en el ad group"] == 25.0
    assert sum(spend.values()) == payload["totals"]["spend"] == 120.0
    assert "familia" in payload["asin_note"]


def test_the_asin_filter_leaves_only_that_asins_search_terms():
    payload = _breakdown(by="search_term", asin="b0hero00001", terms=ASIN_TERMS, product_ads=PRODUCT_ADS)

    assert {row["group"] for row in payload["rows"]} == {"vitamin cream", "night cream"}
    assert payload["totals"]["spend"] == 50.0


def test_an_asin_without_attributed_terms_says_so():
    payload = _breakdown(by="search_term", asin="B0NOTHERE01", terms=ASIN_TERMS, product_ads=PRODUCT_ADS)

    assert payload["rows"] == [] and "B0NOTHERE01" in payload["note"]


def test_the_asin_filter_on_a_campaign_report_dimension_asks_for_the_search_terms():
    with pytest.raises(ValueError, match="source=search_terms"):
        _breakdown(by="campaign", asin="B0HERO00001", terms=ASIN_TERMS, product_ads=PRODUCT_ADS)


def test_a_campaign_breakdown_comes_from_the_campaign_reports_largest_spend_first():
    payload = _breakdown(by="campaign")

    assert [row["group"] for row in payload["rows"]] == ["Camp A", "Camp C", "Camp B"]
    assert payload["rows"][0] == {"group": "Camp A", "spend": 40.0, "sales": 120.0, "orders": 4, "clicks": 40,
                                  "impressions": 200, "acos": 33.3, "cvr": 10.0, "sales_clicks": 120.0,
                                  "orders_clicks": 4, "spend_share": 66.7, "sales_share": 85.7,
                                  "orders_share": 80.0, "clicks_share": 85.1}


def test_the_totals_cover_every_group_so_a_share_of_the_whole_can_be_computed():
    payload = _breakdown(by="campaign", limit=1)

    assert len(payload["rows"]) == 1 and payload["total"] == 3 and "note" in payload
    assert payload["totals"] == {"spend": 60.0, "sales": 140.0, "orders": 5, "clicks": 47, "impressions": 400,
                                 "acos": 42.9, "cvr": 10.64, "sales_clicks": 140.0, "orders_clicks": 5}


def test_a_product_breakdown_splits_the_spend_among_sp_sb_and_sd():
    campaigns = [*CAMPAIGNS, _campaign("Brand Video", product="SB", cost=25.0, clicks=10, sales=90.0, orders=3,
                                       sales_clicks=60.0, orders_clicks=2)]

    rows = {row["group"]: row for row in _breakdown(by="product", campaigns=campaigns)["rows"]}

    assert {group: row["spend"] for group, row in rows.items()} == {"Sponsored Products": 60.0,
                                                                    "Sponsored Brands": 25.0}
    assert (rows["Sponsored Brands"]["sales"], rows["Sponsored Brands"]["sales_clicks"]) == (90.0, 60.0)


def test_a_product_narrows_the_campaign_groups_to_it():
    campaigns = [*CAMPAIGNS, _campaign("Brand Video", product="SB", cost=25.0, clicks=10)]

    payload = _breakdown(by="campaign", product="SB", campaigns=campaigns)

    assert [row["group"] for row in payload["rows"]] == ["Brand Video"]
    assert payload["totals"]["spend"] == 25.0


def test_a_match_type_breakdown_tells_auto_from_the_keyword_types_in_words_the_am_reads():
    groups = {row["group"]: row["spend"] for row in _breakdown(by="match_type")["rows"]}

    assert groups == {"Exact": 30.0, "Broad": 10.0, "Automática": 15.0, "Sin tipo": 5.0}


def test_match_types_and_search_terms_exist_only_for_sponsored_products():
    with pytest.raises(ValueError, match="search terms"):
        _breakdown(by="match_type", product="SB")


def test_a_portfolio_breakdown_names_the_spend_outside_any_portfolio():
    groups = {row["group"]: row["spend"] for row in _breakdown(by="portfolio")["rows"]}

    assert groups == {"Marca": 40.0, "Otro": 15.0, "Sin portfolio": 5.0}


def test_a_search_term_breakdown_adds_up_the_same_term_across_campaigns():
    rows = _breakdown(by="search_term")["rows"]

    assert rows[0] == {"group": "zapatilla", "spend": 35.0, "sales": 140.0, "orders": 5, "clicks": 15,
                       "impressions": 200, "acos": 25.0, "cvr": 33.33, "spend_without_sales": 0.0,
                       "spend_share": 58.3, "sales_share": 100.0, "orders_share": 100.0, "clicks_share": 31.9}


def test_any_metric_can_rank_the_groups():
    assert [row["group"] for row in _breakdown(by="search_term", sort_by="clicks")["rows"]] == [
        "zapatilla roja", "zapatilla", "b0asin"]


def test_ranking_by_acos_leaves_the_groups_that_never_sold_last():
    """Without sales there is no ACoS: those groups go last with a null, never with an invented number."""
    ranked = [row["group"] for row in _breakdown(by="campaign", sort_by="acos")["rows"]]

    assert ranked == ["Camp A", "Camp B", "Camp C"]


def test_a_vendor_account_reads_fourteen_day_orders():
    campaigns = [_campaign("Camp A", cost=10.0, clicks=10, sales=50.0, orders=1, orders_14d=3)]

    payload = _breakdown(by="campaign", campaigns=campaigns, profile={**PROFILE, "account_type": "vendor"})

    assert payload["rows"][0]["orders"] == 3 and payload["attribution_days"] == 14


def test_a_window_without_activity_says_so_instead_of_answering_an_empty_split():
    for by, empty in (("campaign", {"campaigns": []}), ("search_term", {"terms": []})):
        payload = _breakdown(by=by, **empty)

        assert payload["rows"] == [] and payload["totals"] is None and "note" in payload


def test_each_breakdown_says_where_it_comes_from_and_which_window_it_covers():
    by_campaign = _breakdown(by="campaign", days=7)
    by_term = _breakdown(by="search_term", days=7)

    assert "Sponsored Products, Brands y Display" in by_campaign["source"]
    assert "search terms" in by_term["source"] and "Brands" not in by_term["source"]
    assert by_campaign["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}


def test_an_unknown_dimension_is_refused_with_the_ones_that_exist():
    with pytest.raises(ValueError, match="campaign, portfolio, product, match_type, search_term"):
        _breakdown(by="ad_group")


def test_an_unknown_ranking_metric_is_refused_too():
    with pytest.raises(ValueError, match="spend"):
        _breakdown(by="campaign", sort_by="margen")


def test_campaigns_can_still_be_split_from_the_search_terms_on_request():
    rest = _FakeRest(TERMS, CAMPAIGNS)

    payload = amazon_ads.breakdown(rest, profile_id="1111222233334444", by="campaign", source="search_terms")

    assert [name for name, _ in rest.rpc_calls] == ["search_terms_between"]
    assert payload["rows"][0] == {"group": "Camp A", "spend": 40.0, "sales": 120.0, "orders": 4, "clicks": 40,
                                  "impressions": 200, "acos": 33.3, "cvr": 10.0, "spend_without_sales": 10.0,
                                  "spend_share": 66.7, "sales_share": 85.7, "orders_share": 80.0,
                                  "clicks_share": 85.1}
    assert payload["data_source"] == "search_terms" and "source=campaigns" in payload["alternative"]


def test_portfolios_can_still_be_split_from_the_search_terms_on_request():
    groups = {row["group"]: row["spend"] for row in _breakdown(by="portfolio", source="search_terms")["rows"]}

    assert groups == {"Marca": 40.0, "Otro": 15.0, "Sin portfolio": 5.0}


def test_the_campaign_split_tells_how_to_ask_for_the_search_term_one():
    payload = _breakdown(by="campaign")

    assert payload["data_source"] == "campaigns" and "source=search_terms" in payload["alternative"]


def test_the_product_split_from_the_search_terms_is_sponsored_products_alone():
    """The chat asked for it this way in production to compare SP between the two sources."""
    rest = _FakeRest(TERMS, CAMPAIGNS)

    payload = amazon_ads.breakdown(rest, profile_id="1111222233334444", by="product", source="search_terms")

    assert [name for name, _ in rest.rpc_calls] == ["search_terms_between"]
    assert payload["rows"] == [{"group": "Sponsored Products", "spend": 60.0, "sales": 140.0, "orders": 5,
                                "clicks": 47, "impressions": 400, "acos": 42.9, "cvr": 10.64,
                                "spend_without_sales": 25.0, "spend_share": 100.0, "sales_share": 100.0,
                                "orders_share": 100.0, "clicks_share": 100.0}]
    assert payload["data_source"] == "search_terms" and "source=campaigns" in payload["alternative"]


def test_the_product_split_tells_how_to_ask_for_sp_from_the_search_terms():
    assert "source=search_terms" in _breakdown(by="product")["alternative"]


def test_a_split_that_exists_in_the_search_terms_only_offers_no_alternative():
    by_match = _breakdown(by="match_type")

    assert "alternative" not in by_match and by_match["data_source"] == "search_terms"


def test_a_split_asked_from_a_source_that_does_not_have_it_is_refused():
    with pytest.raises(ValueError, match="sólo sale de los search terms"):
        _breakdown(by="match_type", source="campaigns")


def test_the_search_terms_refuse_brands_and_display():
    with pytest.raises(ValueError, match="Sponsored Products"):
        _breakdown(by="campaign", product="SB", source="search_terms")


def test_a_calendar_month_is_split_over_exactly_its_days_and_not_the_last_ones():
    """«Cómo le fue en agosto» needs August's totals, with the campaigns paused since then still in them."""
    rest = _FakeRest(TERMS, CAMPAIGNS)

    payload = amazon_ads.breakdown(rest, profile_id="1111222233334444", by="campaign",
                                   date_from="2026-08-01", date_to="2026-08-31")

    [(name, args)] = [call for call in rest.rpc_calls if call[0] == "campaign_window_totals"]
    assert (args["p_from"], args["p_to"]) == ("2026-08-01", "2026-08-31")
    assert payload["window"] == {"from": "2026-08-01", "to": "2026-08-31", "days": 31}
    assert "window_note" not in payload and payload["totals"]["spend"] == 60.0


def test_the_search_term_split_also_takes_an_exact_period():
    rest = _FakeRest(TERMS, CAMPAIGNS)

    payload = amazon_ads.breakdown(rest, profile_id="1111222233334444", by="search_term",
                                   date_from="2026-09-01", date_to="2026-09-07")

    assert rest.rpc_calls == [("search_terms_between", {"p_profile_id": "1111222233334444", "p_from": "2026-09-01",
                                                         "p_to": "2026-09-07"})]
    assert payload["window"] == {"from": "2026-09-01", "to": "2026-09-07", "days": 7}


def test_a_period_that_starts_before_the_synced_days_is_clipped_and_says_so():
    payload = _breakdown(by="search_term", date_from="2026-07-20", date_to="2026-08-10")

    assert payload["window"] == {"from": "2026-08-01", "to": "2026-08-10", "days": 10}
    assert "se recortó" in payload["window_note"]


def test_the_chat_is_told_a_search_term_split_totals_sponsored_products_and_never_the_account():
    description = {tool["name"]: tool for tool in server.build_tools(object())}["breakdown"]["description"]
    prompt = (Path(__file__).resolve().parents[1] / "ai/agents/orchestrator/prompt.md").read_text(encoding="utf-8")
    by_asin = _breakdown(by="asin", terms=ASIN_TERMS, product_ads=PRODUCT_ADS)

    assert "su totals es el total de la cuenta" in description
    assert "su totals es el de Sponsored Products, no el de la cuenta" in description
    assert "su `totals` es sólo el de Sponsored Products" in prompt
    assert by_asin["source"].startswith("Sólo Sponsored Products") and by_asin["totals"] is not None


def test_a_term_within_its_campaign_is_its_own_group_with_the_spend_it_made_without_selling():
    """Asked for the terms over $20 without sales by campaign, the chat summed each term across campaigns and found
    none: the one that bled did sell in another campaign."""
    rows = _breakdown(by="campaign_search_term", without_sales=True)["rows"]

    assert [(row["group"], row["campaign"], row["spend"], row["spend_without_sales"]) for row in rows] == [
        ("b0asin", "Camp C", 15.0, 15.0), ("zapatilla roja", "Camp A", 10.0, 10.0)]


def test_each_group_says_its_share_of_the_whole_and_where_the_unsold_spend_sits():
    payload = _breakdown(by="match_type")

    assert payload["totals"]["spend_without_sales"] == 25.0
    assert sum(row["spend_without_sales"] for row in payload["rows"]) == 25.0
    assert sum(row["spend_share"] for row in payload["rows"]) == pytest.approx(100.0, abs=0.2)

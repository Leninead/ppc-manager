"""The MCP tools that read what the app's modules compute (services/mcp_server/tools/module_results.py).

They must give the page's numbers for the account, days and values the AM has on screen. No network: an in-memory
PostgREST answers the reads.
"""
import csv
import io

import pytest

from core.ppc_insights.asin_health import health_score
from core.search_term.negatives import (
    AD_GROUP_STATE_UNVERIFIED_NOTE,
    EXACT_GUARD_PARTIAL_NOTE,
    EXCLUDED_CAMPAIGN_NOT_ENABLED,
    EXCLUDED_OWN_KEYWORD,
    RULE_FEW_CLICKS,
    RULE_NO_CONVERSION_CLICKS,
    RULE_NO_CONVERSION_SPEND,
)
from services.mcp_server.tools import amazon_ads, module_results

SEARCH_TERM_COLUMNS = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting",
                       "search_term", "campaign_name", "campaign_status", "ad_group_name", "keyword_text",
                       "ad_keyword_status", "portfolio_id", "portfolio_name", "currency_code", "impressions", "clicks",
                       "purchases_7d", "units_7d", "purchases_14d", "units_14d", "cost", "sales_7d", "sales_14d"]
CAMPAIGN_COLUMNS = ["campaign_id", "name", "state", "targeting_type", "start_date", "budget_amount", "budget_type",
                    "bidding_strategy", "portfolio_id", "portfolio_name", "impressions", "clicks", "cost",
                    "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "currency_code"]


def _term(term, campaign_id, ad_group_id, campaign, *, clicks, orders, cost, sales, portfolio="Brand",
          status="ENABLED", keyword=""):
    return {"campaign_id": campaign_id, "ad_group_id": ad_group_id, "keyword_type": "BROAD", "keyword_id": "1",
            "match_type": "BROAD", "targeting": keyword or term, "search_term": term, "campaign_name": campaign,
            "campaign_status": status, "ad_group_name": "AG", "keyword_text": keyword or term,
            "ad_keyword_status": "ENABLED",
            "portfolio_id": "9", "portfolio_name": portfolio, "currency_code": "USD", "impressions": 500,
            "clicks": clicks, "purchases_7d": orders, "units_7d": orders, "purchases_14d": orders,
            "units_14d": orders, "cost": cost, "sales_7d": sales, "sales_14d": sales}


def _campaign(campaign_id, name, *, state="ENABLED", budget="15.0"):
    return {"campaign_id": campaign_id, "name": name, "state": state, "targeting_type": "MANUAL",
            "start_date": "2026-03-21", "budget_amount": budget, "budget_type": "DAILY", "bidding_strategy": "MANUAL",
            "portfolio_id": "", "portfolio_name": "", "impressions": "0", "clicks": "0", "cost": "0",
            "purchases_7d": "0", "sales_7d": "0", "purchases_14d": "0", "sales_14d": "0", "currency_code": "USD"}


# 103 clicks and 10 orders: a 9.7% CVR, so Rule 2 asks for 21 clicks without an order.
SEARCH_TERMS = [
    # Campaign 3001 still carries the name it had before the AM renamed it.
    _term("luna pajamas", "3001", "4001", "Luna - B0CYLMJJJC - SP - KW - EXACT - Viejo", clicks=40, orders=9,
          cost=30.0, sales=450.0),
    _term("sleep sack", "3002", "4002", "Luna - B0CYLMJJJC - SP - KW - BROAD - Pausada", clicks=50, orders=0,
          cost=40.0, sales=0.0, portfolio="Discovery", status="PAUSED"),
    _term("baby bag", "3009", "4009", "Luna - B0CYLM4L23 - SP - KW - BROAD - Archivada", clicks=5, orders=1,
          cost=4.0, sales=20.0, status="ARCHIVED"),
    _term("cheap toy", "3001", "4001", "Luna - B0CYLMJJJC - SP - KW - EXACT - Viejo", clicks=8, orders=0,
          cost=16.0, sales=0.0),
]
CAMPAIGNS = [
    _campaign("3001", "Luna - B0CYLMJJJC - SP - KW - EXACT - Brand"),
    _campaign("3002", "Luna - B0CYLMJJJC - SP - KW - BROAD - Pausada", state="PAUSED"),
    _campaign("3003", "Luna - B0CYLMJJJC - SP - KW - PHRASE - Fantasma", budget="25.0"),
    _campaign("3004", "Luna - B0CYLM4L23 - SP - AUTO - Chica", budget="5.0"),
]
SETTINGS = {
    "str": {"target_acos": 30, "price": 30.0, "harvest_target_acos": 30, "harvest_price": 30.0,
            "harvest_min_clicks": 15},
    "bid_optimizer": {"target_acos": 40},
    "ppc_insights": {"target_acos": 20, "price": 15.0},
}


def _csv(columns, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class FakeRest:
    def __init__(self, *, currency="USD", settings=SETTINGS, campaigns_synced=True, search_terms=SEARCH_TERMS):
        self.search_terms = search_terms
        self.profile = {"profile_id": "111", "account_id": 1, "cliente": "luna", "account_name": "Luna Kids",
                        "country_code": "US", "currency_code": currency, "account_type": "seller",
                        "timezone": "America/Los_Angeles", "status": "active", "data_from": "2026-07-11",
                        "data_through": "2026-09-14", "refreshed_on": "2026-09-15",
                        "last_success_at": "2026-09-15T10:00:00+00:00", "last_error": ""}
        self.jobs = [{"id": 441, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns",
                      "trigger": "scheduled_daily", "external_account_id": "111", "status": "completed",
                      "window_start": "2026-07-14", "window_end": "2026-09-16", "local_day": "2026-09-17",
                      "finished_at": "2026-09-18T00:51:00+00:00", "created_at": "2026-09-18T00:43:00+00:00"}
                     ] if campaigns_synced else []
        self.settings = settings
        self.reads = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [dict(self.profile)]
        if table == "integration_sync_jobs":
            return [dict(job) for job in self.jobs if params.get("job_kind") == f"eq.{job['job_kind']}"][:1]
        if table == "ai_analysis_settings":
            module = params["module"].removeprefix("eq.")
            return ([{"params": self.settings[module], "updated_by": "ana", "updated_at": "2026-09-17T12:00:00+00:00"}]
                    if module in self.settings else [])
        if table == "ads_product_ad":
            return [{"ad_group_id": "4001", "asin": "B0CYLMJJJC"}, {"ad_group_id": "4002", "asin": "B0CYLMJJJC"}]
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, **_):
        self.reads.append((name, args["p_from"], args["p_to"]))
        if name == "search_terms_between":
            return _csv(SEARCH_TERM_COLUMNS, self.search_terms)
        assert name == "campaigns_between"
        return _csv(CAMPAIGN_COLUMNS, CAMPAIGNS)


class TestFunnelCoverage:
    def test_active_campaigns_without_search_terms_come_largest_budget_first(self):
        payload = module_results.funnel_coverage(FakeRest(), profile_id="111")

        assert [row["campaign"] for row in payload["rows"]] == ["Luna - B0CYLMJJJC - SP - KW - PHRASE - Fantasma",
                                                                "Luna - B0CYLM4L23 - SP - AUTO - Chica"]
        assert payload["rows"][0]["daily_budget"] == 25
        assert payload["matched_by"] == "Campaign ID"

    def test_the_counts_cover_the_three_lists_and_the_renamed_campaign_keeps_its_terms(self):
        counts = module_results.funnel_coverage(FakeRest(), profile_id="111")["counts"]

        assert counts == {"sponsored_products_campaigns": 4, "active_campaigns": 3, "paused_campaigns": 1,
                          "active_campaigns_without_search_terms": 2, "search_term_rows_from_active_campaigns": 2,
                          "search_term_rows_from_paused_or_missing_campaigns": 2,
                          "orders_from_active_campaigns": 9, "sales_from_active_campaigns": 450,
                          "orders_from_paused_or_missing_campaigns": 1, "sales_from_paused_or_missing_campaigns": 20,
                          "orders_from_search_terms": 10, "sales_from_search_terms": 470,
                          "search_terms_without_an_active_campaign": 2, "harvest": 1, "harvest_exact": 1,
                          "harvest_phrase": 0}

    def test_gap_terms_carry_the_state_of_their_campaign_and_the_one_to_create(self):
        payload = module_results.funnel_coverage(FakeRest(), profile_id="111", section="gap_terms",
                                                 match_type="Exact")

        assert [(row["search_term"], row["campaign_state"], row["suggested_campaign"]) for row in payload["rows"]] == [
            ("sleep sack", "PAUSED", "Luna - B0CYLMJJJC - SP - KW - Exact - Sleep Sack"),
            ("baby bag", "No encontrada", "Luna - B0CYLM4L23 - SP - KW - Exact - Baby Bag"),
        ]
        assert payload["parameters"] == {"min_orders": 3, "match_type": "Exact"}

    def test_harvest_follows_the_minimum_on_screen(self):
        payload = module_results.funnel_coverage(FakeRest(), profile_id="111", section="harvest", min_orders=10)

        assert payload["rows"] == [] and payload["counts"]["harvest"] == 0

    def test_harvest_says_which_terms_no_active_campaign_runs_anymore(self):
        payload = module_results.funnel_coverage(FakeRest(), profile_id="111", section="harvest", min_orders=1)

        assert {row["search_term"]: row["in_active_campaign"] for row in payload["rows"]} == {
            "luna pajamas": True, "baby bag": False}

    def test_the_days_on_screen_are_read_for_both_reports(self):
        rest = FakeRest()

        payload = module_results.funnel_coverage(rest, profile_id="111", date_from="2026-09-01", date_to="2026-09-10")

        assert payload["window"] == {"from": "2026-09-01", "to": "2026-09-10", "days": 10}
        assert rest.reads == [("search_terms_between", "2026-09-01", "2026-09-10"),
                              ("campaigns_between", "2026-09-01", "2026-09-10")]

    def test_an_account_without_synced_campaigns_says_so(self):
        with pytest.raises(ValueError, match="todavía no tiene campañas sincronizadas"):
            module_results.funnel_coverage(FakeRest(campaigns_synced=False), profile_id="111")


class TestSearchTermCandidates:
    def test_negatives_follow_the_rules_and_the_price_saved_for_the_account(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111")

        found = {row["search_term"]: (row["rule"], row["action"]) for row in payload["rows"]}
        assert found == {"sleep sack": (RULE_NO_CONVERSION_CLICKS, "Negativo"),
                         "cheap toy": (RULE_NO_CONVERSION_SPEND, "Negativo")}
        assert (payload["parameters"]["clicks_threshold"], payload["parameters"]["spend_threshold"]) == (21, 15.0)
        assert payload["parameters"]["origin"] == "guardados de la cuenta en el Search Term Report"

    def test_a_price_on_screen_replaces_the_saved_one(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111", price=40)

        assert "cheap toy" not in {row["search_term"] for row in payload["rows"] if row["action"] == "Negativo"}
        assert payload["parameters"]["spend_threshold"] == 20.0

    def test_without_a_price_rule_three_does_not_run_and_the_answer_says_so(self):
        payload = module_results.search_term_candidates(FakeRest(currency="MXN", settings={}), profile_id="111")

        rules = {row["search_term"]: row["rule"] for row in payload["rows"]}
        assert rules["cheap toy"] == RULE_FEW_CLICKS
        assert "Regla 3" in payload["parameters_note"]

    def test_the_portfolio_filter_keeps_only_those_portfolios(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111", portfolios=("Discovery",))

        assert [row["search_term"] for row in payload["rows"]] == ["sleep sack"]

    def test_harvest_candidates_carry_their_rule_and_bid(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111", section="harvest")

        (row,) = payload["rows"]
        assert (row["search_term"], row["priority"]) == ("luna pajamas", "Alta")
        assert row["rule"] == "Regla principal + CVR alto + Volumen"
        assert row["suggested_bid"] is not None


class TestSearchTermRowsCarryTheirCampaignState:
    """The report keeps the last name of each campaign («Viejo», «Pausada»): the state says whether it runs."""

    def test_negatives_say_the_state_of_their_campaign_and_their_totals(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111")

        assert {row["search_term"]: row["campaign_state"] for row in payload["rows"]} == {
            "sleep sack": "PAUSED", "cheap toy": "ENABLED"}
        assert payload["totals"] == {"spend": 56, "clicks": 58, "impressions": 1000}

    def test_harvest_says_the_state_of_its_campaign_and_its_totals(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111", section="harvest")

        assert [(row["search_term"], row["campaign_state"]) for row in payload["rows"]] == [("luna pajamas", "ENABLED")]
        assert payload["totals"] == {"clicks": 40, "orders": 9}

    def test_the_top_search_terms_say_the_state_of_their_campaign(self):
        payload = amazon_ads.top_search_terms(FakeRest(), profile_id="111")

        assert {row["Customer Search Term"]: row["Campaign Status"] for row in payload["rows"]} == {
            "luna pajamas": "ENABLED", "sleep sack": "PAUSED", "baby bag": "ARCHIVED", "cheap toy": "ENABLED"}


class TestNegativesSayWhetherTheyGoIntoTheBulk:
    """The page's bulk leaves some candidates out: the chat promised the spend of negatives nobody uploads."""

    def test_each_negative_carries_the_verdict_of_the_modules_bulk(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111")

        assert {row["search_term"]: (row["in_bulk"], row["bulk_exclusion"]) for row in payload["rows"]} == {
            "sleep sack": (False, EXCLUDED_CAMPAIGN_NOT_ENABLED.format(status="PAUSED")),
            # Its own keyword is "cheap toy": negating it would cut the ad group's own traffic.
            "cheap toy": (False, EXCLUDED_OWN_KEYWORD)}
        assert payload["totals_in_bulk"] == {"spend": 0, "clicks": 0, "impressions": 0}
        assert payload["bulk_notes"] == [EXACT_GUARD_PARTIAL_NOTE, AD_GROUP_STATE_UNVERIFIED_NOTE]

    def test_the_bulk_total_counts_only_the_negatives_that_go_into_it(self):
        broad_toy = _term("cheap toy", "3001", "4001", "Luna - B0CYLMJJJC - SP - KW - EXACT - Viejo", clicks=8,
                          orders=0, cost=16.0, sales=0.0, keyword="toy")
        rest = FakeRest(search_terms=[*SEARCH_TERMS[:3], broad_toy])

        payload = module_results.search_term_candidates(rest, profile_id="111")

        assert {row["search_term"]: row["in_bulk"] for row in payload["rows"]} == {"sleep sack": False,
                                                                                   "cheap toy": True}
        assert payload["totals_in_bulk"] == {"spend": 16, "clicks": 8, "impressions": 500}
        assert payload["totals"] == {"spend": 56, "clicks": 58, "impressions": 1000}

    def test_harvest_has_no_bulk_verdict(self):
        payload = module_results.search_term_candidates(FakeRest(), profile_id="111", section="harvest")

        assert "totals_in_bulk" not in payload and "in_bulk" not in payload["rows"][0]


def test_without_saved_parameters_each_tool_says_it_used_the_module_defaults():
    rest = FakeRest(settings={})

    origins = [module_results.search_term_candidates(rest, profile_id="111")["parameters"]["origin"],
               module_results.bid_suggestions(rest, profile_id="111")["parameters"]["origin"],
               module_results.asin_health(rest, profile_id="111")["parameters"]["origin"]]

    assert all(origin.endswith("la cuenta no guardó parámetros") for origin in origins)
    assert origins[0].startswith("valores por defecto del Search Term Report")


class TestBidSuggestions:
    def test_the_bid_per_asin_uses_the_target_saved_for_the_account(self):
        payload = module_results.bid_suggestions(FakeRest(), profile_id="111")

        assert [(row["asin"], row["status"]) for row in payload["rows"]] == [("B0CYLMJJJC", "OK"),
                                                                             ("B0CYLM4L23", "REVISAR")]
        # 9 orders over 98 clicks, a 50.00 average ticket and a 40% target.
        assert payload["rows"][0]["suggested_bid"] == 1.84
        assert payload["parameters"] == {"target_acos": 40, "origin": "guardado de la cuenta en el Bid Optimizer"}

    def test_a_target_on_screen_replaces_the_saved_one(self):
        payload = module_results.bid_suggestions(FakeRest(), profile_id="111", target_acos=25)

        assert payload["rows"][0]["suggested_bid"] == 1.15
        assert payload["parameters"]["origin"] == "pedido en la llamada"


class TestAsinHealth:
    def test_each_asin_scores_with_the_target_saved_for_the_account(self):
        payload = module_results.asin_health(FakeRest(), profile_id="111")

        assert [row["asin"] for row in payload["rows"]] == ["B0CYLMJJJC", "B0CYLM4L23"]
        first = payload["rows"][0]
        assert first["health_score"] == health_score(86 / 450 * 100, 20, 9 / 98 * 100, None, None, None)
        assert first["top_search_terms"][0] == "luna pajamas"
        assert payload["asin_source"] == "attributed"
        assert payload["parameters"]["target_acos"] == 20


class TestRequestedWindow:
    def _profile(self):
        return amazon_ads._profile(FakeRest(), "111")

    def test_dates_inside_the_synced_data_are_kept_exactly(self):
        assert amazon_ads.requested_window(self._profile(), 7, "2026-09-01", "2026-09-10")[:2] == (
            amazon_ads.date(2026, 9, 1), amazon_ads.date(2026, 9, 10))

    def test_dates_past_the_synced_data_are_clipped_and_said(self):
        start, end, note = amazon_ads.requested_window(self._profile(), 7, "2026-09-10", "2026-09-20")

        assert (start, end) == (amazon_ads.date(2026, 9, 10), amazon_ads.date(2026, 9, 14))
        assert "se recortó" in note

    @pytest.mark.parametrize("date_from, date_to, message", [
        ("2026-09-10", "2026-09-01", "anterior"),
        ("2026-07-01", "2026-09-14", "hasta 60 días"),
        ("10/09/2026", "2026-09-14", "AAAA-MM-DD"),
        ("2026-01-01", "2026-01-31", "queda afuera"),
    ])
    def test_impossible_dates_are_refused_in_words(self, date_from, date_to, message):
        with pytest.raises(ValueError, match=message):
            amazon_ads.requested_window(self._profile(), 7, date_from, date_to)

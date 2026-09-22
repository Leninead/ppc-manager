"""What each module tells the chat about its screen: the account, the days, the values and the calls behind them."""
from datetime import date

import pandas as pd

from core.amazon_ads.campaign_analyzer import CampaignAnalyzerParams
from core.amazon_ads.campaign_provider import CampaignSource
from core.chat.screen_selection import FROM_AMAZON_ADS, FROM_HAND_UPLOAD, HAND_UPLOAD_NOTE, OLDER_DATA_NOTE
from core.search_term.frame import SOURCE_API, SOURCE_FILE, SearchTermSource
from modules.pages import (
    bid_optimizer,
    bulk_campanas,
    datadive_analyzer,
    ppc_insights,
    search_query_performance,
    search_term_report,
)

WINDOW = (("profile_id", "111"), ("date_from", "2026-09-14"), ("date_to", "2026-09-20"))


def _search_terms(source=SOURCE_API, **overrides) -> SearchTermSource:
    values = {"frame": pd.DataFrame(), "source": source, "currency_code": "USD", "label": "Luna Kids · US",
              "signature": "s", "attribution_days": 7, "bulk_ready": source == SOURCE_API, "profile_id": "111",
              "window_start": date(2026, 9, 14), "window_end": date(2026, 9, 20)}
    values.update(overrides)
    return SearchTermSource(**values)


def _calls(selection):
    return [(call.name, dict(call.arguments)) for call in selection.calls]


class TestSearchTermReport:
    def test_the_two_candidate_lists_are_called_with_the_values_on_screen(self):
        selection = search_term_report.screen_selection(
            _search_terms(), target_acos=30, price=30.0, harvest_price=None, harvest_target_acos=35,
            harvest_min_clicks=15, portfolios=("Brand",))

        assert (selection.source, selection.profile_id) == (FROM_AMAZON_ADS, "111")
        assert _calls(selection) == [
            ("search_term_candidates", {**dict(WINDOW), "section": "negatives", "price": 30.0,
                                        "portfolios": ["Brand"]}),
            ("search_term_candidates", {**dict(WINDOW), "section": "harvest", "harvest_target_acos": 35,
                                        "harvest_min_clicks": 15, "portfolios": ["Brand"]}),
        ]
        assert dict(selection.values)["precio de harvest"] == "sin precio"
        assert dict(selection.values)["portfolios filtrados"] == "Brand"

    def test_a_file_has_no_call_and_says_the_tools_cannot_see_it(self):
        selection = search_term_report.screen_selection(
            _search_terms(SOURCE_FILE, label="str.csv", profile_id=""), target_acos=30, price=None,
            harvest_price=None, harvest_target_acos=30, harvest_min_clicks=15)

        assert (selection.calls, selection.source, selection.notes) == ((), FROM_HAND_UPLOAD, (HAND_UPLOAD_NOTE,))
        assert selection.profile_id == ""

    def test_older_data_on_screen_is_warned(self):
        selection = search_term_report.screen_selection(
            _search_terms(), target_acos=30, price=30.0, harvest_price=30.0, harvest_target_acos=30,
            harvest_min_clicks=15, older_data=True)

        assert selection.notes == (OLDER_DATA_NOTE,)


class TestBidOptimizer:
    def test_the_target_on_screen_travels_and_an_uploaded_inventory_is_warned(self):
        selection = bid_optimizer.screen_selection(_search_terms(), target_acos=25, inventory_uploaded=True,
                                                   older_data=False)

        assert _calls(selection) == [("bid_suggestions", {**dict(WINDOW), "target_acos": 25})]
        assert selection.profile_id == "111"
        assert selection.notes == (bid_optimizer.INVENTORY_NOTE,)
        assert dict(selection.values)["precio"] == "Inventory Report (precio de lista)"


class TestPpcInsights:
    def test_optional_files_are_named_as_the_part_the_tools_cannot_see(self):
        selection = ppc_insights.screen_selection(_search_terms(), target_acos=20, price=15.0,
                                                  uploaded_files=("SQP",), older_data=False)

        assert _calls(selection) == [("asin_health", {**dict(WINDOW), "target_acos": 20})]
        assert selection.profile_id == "111"
        assert selection.notes[0].startswith("SQP se subieron a mano")
        assert dict(selection.values)["archivos opcionales"] == "SQP"


class TestBulkCampanas:
    def _source(self):
        return CampaignSource(frame=pd.DataFrame(), currency_code="USD", label="Luna Kids · US", profile_id="111",
                              window_start=date(2026, 9, 14), window_end=date(2026, 9, 20), attribution_days=7)

    def test_the_product_and_the_thresholds_on_screen_reach_both_tools(self):
        selection = bulk_campanas.screen_selection(self._source(), product_choice="Sponsored Brands",
                                                   params=CampaignAnalyzerParams(35.0, 20.0, 3))

        assert _calls(selection) == [
            ("campaign_health", {**dict(WINDOW), "product": "SB", "target_acos": 35.0, "spend_to_pause": 20.0,
                                 "min_orders_to_scale": 3}),
            ("idle_targets", {**dict(WINDOW), "product": "SB"}),
        ]
        assert selection.profile_id == "111"

    def test_all_products_and_no_metrics_call_without_filters_or_thresholds(self):
        selection = bulk_campanas.screen_selection(self._source(), product_choice="Todos", params=None)

        assert _calls(selection) == [("campaign_health", dict(WINDOW)), ("idle_targets", dict(WINDOW))]
        assert dict(selection.values) == {"producto": "Todos"}

    def test_a_file_names_the_upload_as_the_account(self):
        selection = bulk_campanas.screen_selection(None, product_choice="Todos", params=None)

        assert (selection.account, selection.calls, selection.profile_id) == (
            bulk_campanas.HAND_UPLOAD_ACCOUNT, (), "")


class TestSearchQueryPerformance:
    def test_the_file_the_brand_and_the_week_travel_with_the_terms_typed(self):
        selection = search_query_performance.screen_selection("sqp_semana.csv", "wamery", "2026-09-13",
                                                              ["wamery", "wa"])

        assert (selection.account, selection.profile_id) == ("la marca wamery", "")
        assert dict(selection.values) == {"archivo": "sqp_semana.csv", "semana": "2026-09-13",
                                          "brand terms": "wamery, wa"}
        assert selection.notes == (HAND_UPLOAD_NOTE,)

    def test_the_week_comes_from_the_reporting_date_column(self):
        frame = pd.DataFrame({"Reporting Date": [None, "2026-09-13"], "Search Query": ["a", "b"]})

        assert search_query_performance.report_week(frame) == "2026-09-13"
        assert search_query_performance.report_week(pd.DataFrame({"Search Query": ["a"]})) == "no declarada"


class TestDataDive:
    def test_a_niche_from_the_api_travels_with_its_ids_for_the_datadive_tools(self):
        selection = datadive_analyzer.screen_selection(
            niche_id="n-1", niche_label="Collagen powder", marketplace="US", file_name="", my_asin="B0CYLMJJJC",
            min_sv=100, min_relevance=1.0, radar=("r-9", "2026-08-22", "2026-09-21"))

        assert (selection.account, selection.profile_id) == ("el niche Collagen powder · US", "")
        assert dict(selection.values)["niche_id"] == "n-1"
        assert dict(selection.values)["rank radar"] == "radar_id r-9, del 2026-08-22 al 2026-09-21"

    def test_nothing_loaded_is_no_selection(self):
        assert datadive_analyzer.screen_selection(niche_id="", niche_label="", marketplace="", file_name="",
                                                  my_asin="", min_sv=100, min_relevance=1.0, radar=None) is None

"""PPC Audit Pro's rules over frames shaped like a Bulk File: the inherited ones, and the corrections of IT-44."""
import math

import pandas as pd
import pytest

from core.ppc_audit.checks import (
    AUTO_FROM_SEARCH_TERMS,
    AUTO_FROM_TARGETING,
    GRADUATE_KEEP,
    GRADUATE_PAUSE,
    GRADUATE_PAUSED,
    GRADUATE_RAISE,
    GRADUATE_SKAG,
    acos,
    business_report_figures,
    duplicate_keywords,
    graduation_targets,
    placement_adjustments,
    product_totals,
    run_audit,
    running_rows,
    target_types,
    top_campaigns,
    wasted_terms,
)
from core.ppc_audit.frames import SB_SEARCH_TERMS, SD_TARGETS, SP_TARGET_METRICS, AuditFrames
from core.search_term.frame import SOURCE_FILE

PARTS = ("sp_campaigns", "sp_ad_groups", "sp_keywords", "sp_product_targets", "sp_product_ads", "sp_placements",
         "sp_search_terms", "sb_campaigns", "sb_keywords", "sb_search_terms", "sd_campaigns", "sd_targets")


def _frames(unavailable=None, **parts) -> AuditFrames:
    frames = {part: pd.DataFrame() for part in PARTS}
    frames.update({part: pd.DataFrame(rows) for part, rows in parts.items()})
    return AuditFrames(**frames, source=SOURCE_FILE, unavailable=dict(unavailable or {}))


def _campaign(campaign_id, name, *, state="enabled", targeting="Manual", spend=0.0, sales=0.0, clicks=0,
              impressions=0, orders=0, strategy="Fixed bid") -> dict:
    return {"Campaign ID": campaign_id, "Campaign Name": name, "State": state, "Targeting Type": targeting,
            "Bidding Strategy": strategy, "Spend": spend, "Sales": sales, "Clicks": clicks,
            "Impressions": impressions, "Orders": orders}


def _keyword(campaign_id, text, match="Exact", *, ad_group="AG1", state="enabled", spend=0.0, sales=0.0,
             orders=0, clicks=0, impressions=0, bid=0.5, name="") -> dict:
    return {"Campaign ID": campaign_id, "Campaign Name": name, "Ad Group ID": ad_group,
            "Ad Group Name": f"Ad group {ad_group}", "Keyword Text": text, "Match Type": match, "State": state,
            "Bid": bid, "Spend": spend, "Sales": sales, "Orders": orders, "Clicks": clicks,
            "Impressions": impressions}


def _target(campaign_id, expression, *, ad_group="AG1", state="enabled", spend=0.0, sales=0.0, orders=0, clicks=0,
            impressions=0) -> dict:
    return {"Campaign ID": campaign_id, "Ad Group ID": ad_group, "Product Targeting Expression": expression,
            "State": state, "Spend": spend, "Sales": sales, "Orders": orders, "Clicks": clicks,
            "Impressions": impressions}


def test_acos_is_zero_when_nothing_sold_as_the_module_always_showed():
    assert acos(50, 0) == 0
    assert acos(25, 100) == 25


def test_product_totals_sum_the_known_campaigns_and_count_the_unknown_apart():
    campaigns = pd.DataFrame([_campaign("1", "A", spend=10, sales=40, clicks=5, impressions=100, orders=2),
                              _campaign("2", "B", spend=math.nan, sales=math.nan, clicks=math.nan,
                                        impressions=math.nan, orders=math.nan)])

    totals = product_totals(campaigns)

    assert (totals.spend, totals.sales, totals.clicks, totals.impressions, totals.orders) == (10, 40, 5, 100, 2)
    assert (totals.campaigns, totals.unknown) == (2, 1)


def test_the_business_report_gives_revenue_organic_sales_and_tacos():
    report = pd.DataFrame({"(Child) ASIN": ["B0A", "B0B"], "Ordered Product Sales": ["$1,000.00", "$500.00"]})

    figures = business_report_figures(report, ppc_spend=150, ppc_sales=600)

    assert figures.revenue == 1500
    assert figures.organic_sales == 900
    assert figures.organic_pct == pytest.approx(60)
    assert figures.tacos == pytest.approx(10)


def test_a_business_report_without_ordered_sales_or_revenue_gives_nothing():
    assert business_report_figures(pd.DataFrame({"Sessions": [5]}), 10, 10) is None
    assert business_report_figures(pd.DataFrame({"Ordered Product Sales": ["$0.00"]}), 10, 10) is None
    assert business_report_figures(None, 10, 10) is None


def test_what_runs_leaves_out_paused_keywords_campaigns_and_ad_groups_but_not_unlisted_ones():
    campaigns = pd.DataFrame([_campaign("1", "On"), _campaign("2", "Off", state="paused")])
    ad_groups = pd.DataFrame([{"Ad Group ID": "AG1", "State": "enabled"}, {"Ad Group ID": "AG2", "State": "paused"},
                              {"Ad Group ID": "AG3", "State": "archived"}])
    keywords = pd.DataFrame([_keyword("1", "runs"), _keyword("1", "paused keyword", state="paused"),
                             _keyword("2", "paused campaign"), _keyword("1", "paused group", ad_group="AG2"),
                             _keyword("1", "archived group", ad_group="AG3"), _keyword("1", "unlisted group",
                                                                                     ad_group="AG9"),
                             _keyword("9", "unlisted campaign")])

    running = running_rows(keywords, campaigns, ad_groups)

    assert list(running["Keyword Text"]) == ["runs", "unlisted group", "unlisted campaign"]


def test_mixed_match_types_are_counted_by_campaign_id_over_what_runs():
    frames = _frames(
        sp_campaigns=[_campaign("1", "Twin"), _campaign("2", "Twin"), _campaign("3", "Paused broad")],
        sp_keywords=[_keyword("1", "a", "Exact"), _keyword("2", "b", "Broad"),
                     _keyword("3", "c", "Exact"), _keyword("3", "d", "Broad", state="paused"),
                     _keyword("4", "e", "Exact", name="Mixed"), _keyword("4", "f", "Phrase", name="Mixed")],
    )

    result = run_audit(frames)

    assert result.mixed_match_campaigns == ["Mixed"]
    assert result.mixed_match.iloc[0].to_dict() == {"Campaign Name": "Mixed", "Match Types": "Exact | Phrase",
                                                    "Keywords": 2}
    assert result.sp_match_types == {"Exact": 3, "Phrase": 1, "Broad": 1}


def test_target_waste_counts_sp_sb_and_sd_targets_over_the_spend_of_all_three():
    frames = _frames(
        sp_keywords=[_keyword("1", "a", spend=30, sales=0), _keyword("1", "b", spend=70, sales=200),
                     _keyword("1", "unknown", spend=math.nan, sales=math.nan)],
        sp_product_targets=[_target("1", 'asin="B0COMPET01"', spend=20, sales=0)],
        sb_keywords=[_keyword("5", "brand", spend=10, sales=0)],
        sd_targets=[_target("7", 'views=(exactProduct lookback=30)', spend=40, sales=80)],
    )

    waste = run_audit(frames).target_waste

    assert (waste.sp.waste, waste.sp.count, waste.sp.spend) == (50, 2, 120)
    assert (waste.sb.waste, waste.sd.waste) == (10, 0)
    assert waste.total_waste == 60
    assert waste.pct == pytest.approx(60 / 170 * 100)


def test_a_part_the_source_lacks_has_no_waste_line_and_stays_out_of_the_totals():
    frames = _frames(unavailable={SD_TARGETS: "sin targets SD", SP_TARGET_METRICS: "sin métricas"},
                     sp_keywords=[_keyword("1", "a", spend=math.nan)],
                     sb_keywords=[_keyword("5", "brand", spend=10, sales=0)],
                     sd_targets=[_target("7", "x", spend=40)])

    waste = run_audit(frames).target_waste

    assert waste.sp is None and waste.sd is None
    assert (waste.total_waste, waste.pct) == (10, 100)


def test_search_term_waste_rates_sp_and_lists_the_terms_that_spent_the_most_without_selling():
    frames = _frames(
        sp_search_terms=[{"Customer Search Term": term, "Spend": spend, "Sales": sales, "Clicks": 3,
                          "Impressions": 90} for term, spend, sales in (("cheap", 5, 0), ("costly", 12, 0),
                                                                        ("seller", 20, 90), ("free", 0, 0))],
        sb_search_terms=[{"Customer Search Term": "brand", "Spend": 8, "Sales": 0}],
    )

    waste = run_audit(frames).search_term_waste

    assert (waste.sp.waste, waste.sp.count, waste.sp.spend) == (17, 2, 37)
    assert waste.pct == pytest.approx(17 / 37 * 100)
    assert waste.sb.waste == 8 and waste.total_waste == 25
    assert list(waste.top_terms["Customer Search Term"]) == ["costly", "cheap"]
    assert list(waste.top_terms.columns) == ["Customer Search Term", "Spend", "Clicks", "Impressions"]


def test_sb_search_terms_the_source_lacks_have_no_line():
    frames = _frames(unavailable={SB_SEARCH_TERMS: "sin sincronizar"},
                     sp_search_terms=[{"Customer Search Term": "x", "Spend": 4, "Sales": 0}])

    assert run_audit(frames).search_term_waste.sb is None


def test_sp_segments_split_keywords_product_targets_and_the_auto_groups_of_the_targeting_report():
    frames = _frames(
        sp_campaigns=[_campaign("1", "Manual", spend=60, sales=100, clicks=30, impressions=1000, orders=4),
                      _campaign("2", "Auto", targeting="Auto", spend=40, sales=20, clicks=20, impressions=4000,
                                orders=1)],
        sp_keywords=[_keyword("1", "a", "Exact", spend=10, sales=40, clicks=5, impressions=100, orders=2),
                     _keyword("1", "b", "Broad", spend=20, sales=0, clicks=10, impressions=300)],
        sp_product_targets=[_target("1", 'asin="B0COMPET01"', spend=20, sales=50, clicks=10, impressions=500,
                                    orders=2),
                            _target("1", 'category="123"', spend=10, sales=10, clicks=5, impressions=100),
                            _target("2", "close-match", spend=25, sales=20, clicks=12, impressions=3000, orders=1),
                            _target("2", "substitutes", spend=15, sales=0, clicks=8, impressions=1000)],
        sp_search_terms=[{"Customer Search Term": "x", "Campaign ID": "2", "Product Targeting Expression":
                          "loose-match", "Spend": 99, "Sales": 0}],
    )

    result = run_audit(frames)
    segments = result.sp_segments.set_index("Segmento")

    assert result.auto_segments_source == AUTO_FROM_TARGETING
    assert segments.loc["KW Exact", ["# Targets", "Spend", "Sales", "ACoS", "CTR", "CVR", "CPC"]].tolist() == \
        [1, 10, 40, 25.0, 5.0, 40.0, 2.0]
    assert segments.loc["PT ASIN Targeting", "Spend"] == 20
    assert segments.loc["PT Category Targeting", "Spend"] == 10
    assert segments.loc["AUTO Close Match", "Spend"] == 25
    assert segments.loc["AUTO Loose Match", "Spend"] == 0
    assert segments.loc["AUTO Substitutes", "Spend"] == 15
    assert segments.loc["TOTAL SP", ["# Targets", "Spend", "% Spend"]].tolist() == [2, 100, 100.0]
    assert segments.loc["KW Broad", "% Spend"] == 20.0
    assert list(result.sp_segments.columns) == ["Segmento", "# Targets", "Spend", "Sales", "ACoS", "Clicks",
                                                "Orders", "CTR", "CVR", "CPC", "% Spend"]


def test_without_auto_groups_in_the_source_the_auto_segments_come_from_the_auto_campaigns_search_terms():
    frames = _frames(
        sp_campaigns=[_campaign("2", "Auto", targeting="Auto", spend=40), _campaign("1", "Manual", spend=10)],
        sp_search_terms=[
            {"Customer Search Term": "a", "Campaign ID": "2", "Product Targeting Expression": "close-match",
             "Spend": 5, "Sales": 10, "Clicks": 2, "Impressions": 20, "Orders": 1},
            {"Customer Search Term": "b", "Campaign ID": "2", "Product Targeting Expression": "complements",
             "Spend": 3, "Sales": 0, "Clicks": 1, "Impressions": 9, "Orders": 0},
            {"Customer Search Term": "c", "Campaign ID": "1", "Product Targeting Expression": "close-match",
             "Spend": 50, "Sales": 0, "Clicks": 9, "Impressions": 90, "Orders": 0},
        ],
    )

    result = run_audit(frames)
    segments = result.sp_segments.set_index("Segmento")

    assert result.auto_segments_source == AUTO_FROM_SEARCH_TERMS
    assert (segments.loc["AUTO Close Match", "Spend"], segments.loc["AUTO Complements", "Spend"]) == (5, 3)


def test_sb_and_sd_segments_follow_their_keywords_and_campaign_names():
    frames = _frames(
        sb_campaigns=[_campaign("5", "SB brand", spend=30, sales=90)],
        sb_keywords=[_keyword("5", "brand", "Exact", spend=20, sales=90), _keyword("5", "gen", "Broad", spend=10)],
        sd_campaigns=[_campaign("7", "SD Remarketing views", spend=10, sales=40),
                      _campaign("8", "SD audience in-market", spend=5), _campaign("9", "SD competitors", spend=5)],
    )

    result = run_audit(frames)

    sb = result.sb_segments.set_index("Segmento")
    assert (sb.loc["KW Exact", "Spend"], sb.loc["KW Broad", "Spend"], sb.loc["TOTAL SB", "Spend"]) == (20, 10, 30)
    sd = result.sd_segments.set_index("Segmento")
    assert sd["Spend"].to_dict() == {"SD Retargeting": 10, "SD Audiences": 5, "SD Product Targeting": 5,
                                     "TOTAL SD": 20}


def test_an_ad_product_without_campaigns_has_no_segments():
    result = run_audit(_frames())

    assert result.sb_segments.empty and result.sd_segments.empty


def test_top_campaigns_rank_by_spend_and_compute_their_acos():
    campaigns = pd.DataFrame([_campaign("1", "Small", spend=5, sales=10, orders=1),
                              _campaign("2", "Big", spend=80, sales=0),
                              _campaign("3", "Unknown", spend=math.nan, sales=math.nan),
                              _campaign("4", "Mid", spend=40, sales=160, orders=4)])

    top = top_campaigns(campaigns, limit=3)

    assert list(top["Campaign Name"]) == ["Big", "Mid", "Small"]
    assert list(top["ACOS"]) == [0, 25.0, 50.0]
    assert list(top.columns) == ["Campaign Name", "Targeting Type", "Spend", "Sales", "ACOS", "Orders"]
    assert len(top_campaigns(campaigns, limit=None)) == 4


def test_target_types_need_brand_terms_and_tell_own_asins_from_competitors():
    keywords = pd.DataFrame([_keyword("1", "luna pajamas", spend=10, sales=40), _keyword("1", "kids pajamas",
                                                                                         spend=20)])
    targets = pd.DataFrame([_target("1", 'asin="B0OWN00001"', spend=5, sales=20),
                            _target("1", 'asin-expanded-from="B0COMPET01"', spend=15),
                            _target("1", 'category="123"', spend=10, sales=5)])

    assert target_types(keywords, targets, (), set()).empty
    types = target_types(keywords, targets, ("luna",), {"B0OWN00001"}).set_index("Tipo")

    assert types["Targets"].to_dict() == {"generic": 2, "competitor_asin": 1, "own_brand": 1, "own_asin": 1}
    assert types.loc["own_brand", "ACoS"] == 25.0
    assert types.loc["generic", "% Spend"] == 50.0


def test_the_advertised_asins_are_own_asins_in_the_audit():
    frames = _frames(sp_product_targets=[_target("1", 'asin="B0OWN00001"', spend=5)],
                     sp_product_ads=[{"Campaign ID": "1", "ASIN": "b0own00001"}])

    types = run_audit(frames, brand_terms=("luna",)).target_types

    assert list(types["Tipo"]) == ["own_asin"]


def test_duplicate_keywords_are_the_same_text_and_match_type_in_two_or_more_campaigns():
    keywords = pd.DataFrame([_keyword("1", "Luna Pajamas", spend=10, sales=5), _keyword("2", " luna pajamas ",
                                                                                         spend=3),
                             _keyword("3", "luna pajamas", "Broad", spend=90),
                             _keyword("1", "solo", spend=50), _keyword("2", "twice", spend=1),
                             _keyword("3", "twice", spend=1)])

    duplicates = duplicate_keywords(keywords)

    assert duplicates.to_dict("records") == [
        {"Keyword": "luna pajamas", "Match Type": "Exact", "# Campañas": 2, "Spend_Total": 13.0, "Sales_Total": 5.0},
        {"Keyword": "twice", "Match Type": "Exact", "# Campañas": 2, "Spend_Total": 2.0, "Sales_Total": 0.0}]
    assert len(duplicate_keywords(keywords, limit=1)) == 1


def test_a_paused_copy_of_a_keyword_is_not_a_duplicate():
    frames = _frames(sp_campaigns=[_campaign("1", "A"), _campaign("2", "B", state="paused")],
                     sp_keywords=[_keyword("1", "luna"), _keyword("2", "luna")])

    assert run_audit(frames).duplicates.empty


def test_placements_read_the_enabled_campaigns_with_campaign_manager_names():
    campaigns = pd.DataFrame([_campaign("1", "On"), _campaign("2", "On too"), _campaign("3", "Off",
                                                                                      state="archived")])
    placements = pd.DataFrame([
        {"Campaign ID": "1", "Placement": "PLACEMENT_TOP", "Percentage": 50},
        {"Campaign ID": "2", "Placement": "PLACEMENT_TOP", "Percentage": 0},
        {"Campaign ID": "3", "Placement": "PLACEMENT_TOP", "Percentage": 900},
        {"Campaign ID": "1", "Placement": "PLACEMENT_PRODUCT_PAGE", "Percentage": 0},
    ])

    table = placement_adjustments(placements, campaigns).set_index("Placement")

    assert table.loc["Top of Search", ["Campañas", "Promedio", "Min", "Max", "Con_Ajuste"]].tolist() == \
        [2, 25.0, 0, 50, 1]
    assert table.loc["Product Pages", "Con_Ajuste"] == 0


def test_the_bidding_strategies_count_each_enabled_campaign_once():
    frames = _frames(sp_campaigns=[_campaign("1", "A", strategy="Fixed bid"),
                                   _campaign("2", "B", strategy="Dynamic bids - down only"),
                                   _campaign("3", "C", strategy="Fixed bid"),
                                   _campaign("4", "D", strategy="Fixed bid", state="paused")],
                     sp_placements=[{"Campaign ID": "1", "Placement": "PLACEMENT_TOP", "Percentage": 10,
                                     "Bidding Strategy": "Fixed bid"}] * 4)

    strategies = run_audit(frames).bidding_strategies

    assert dict(zip(strategies["Bidding Strategy"], strategies["Count"])) == {"Fixed bid": 2,
                                                                               "Dynamic bids - down only": 1}


def test_skag_counts_the_targets_that_run_in_each_enabled_manual_campaign_with_or_without_traffic():
    frames = _frames(
        sp_campaigns=[_campaign("1", "Skag"), _campaign("2", "Normal"), _campaign("3", "Bag"),
                      _campaign("4", "Auto", targeting="Auto"), _campaign("5", "Paused", state="paused")],
        sp_keywords=[_keyword("1", "only", spend=5), _keyword("1", "paused one", state="paused", spend=9)]
                    + [_keyword("2", f"k{index}", spend=1) for index in range(3)]
                    + [_keyword("3", f"b{index}") for index in range(12)]
                    + [_keyword("5", "p1"), _keyword("5", "p2")],
        sp_product_targets=[_target("4", "close-match", spend=30), _target("2", 'asin="B0X0000001"', spend=2)],
    )

    skag = run_audit(frames).skag.set_index("Tipo")

    assert skag["Campañas"].to_dict() == {"Bolsa (11+)": 1, "Normal (2-10)": 1, "SKAG (1 target)": 1}
    assert skag.loc["Normal (2-10)", "Spend_Total"] == 5
    assert skag.loc["SKAG (1 target)", "% Spend"] == 50.0


def test_graduation_lists_quiet_keywords_of_campaigns_with_traffic_with_their_recommendation():
    keywords = pd.DataFrame([
        _keyword("1", "busy", impressions=500),
        _keyword("1", "sold before", impressions=0, sales=30, orders=1),
        _keyword("1", "spent without orders", impressions=0, spend=4),
        _keyword("1", "luna brand", impressions=0),
        _keyword("1", "never anything", impressions=0),
        _keyword("1", "paused itself", impressions=0, state="paused"),
        _keyword("1", "paused ad group", impressions=0, ad_group="AG2"),
        _keyword("1", "unknown metrics", impressions=math.nan),
        _keyword("2", "quiet campaign", impressions=0),
    ])
    ad_groups = pd.DataFrame([{"Ad Group ID": "AG1", "State": "enabled"}, {"Ad Group ID": "AG2", "State": "paused"}])

    graduation = graduation_targets(keywords, ad_groups, ("luna",))

    assert dict(zip(graduation["Keyword Text"], graduation["Recomendación"])) == {
        "sold before": GRADUATE_RAISE, "spent without orders": GRADUATE_PAUSE, "luna brand": GRADUATE_KEEP,
        "never anything": GRADUATE_SKAG, "paused itself": GRADUATE_PAUSED}
    assert set(graduation["Campaign Impressions"]) == {500}


def test_graduation_without_quiet_keywords_is_empty():
    keywords = pd.DataFrame([_keyword("1", "busy", impressions=10)])

    assert graduation_targets(keywords, pd.DataFrame()).empty


def test_wasted_terms_can_list_them_all():
    terms = pd.DataFrame([{"Customer Search Term": f"t{index}", "Spend": index + 1, "Sales": 0}
                          for index in range(8)])

    assert len(wasted_terms(terms)) == 5
    assert len(wasted_terms(terms, limit=None)) == 8

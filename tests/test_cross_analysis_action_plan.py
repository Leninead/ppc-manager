"""Plan de Acción of Análisis Cruzado: the classifier moved out of the page, pinned branch by branch. No network."""
import math

import pandas as pd
import pytest

from core.cross_analysis.action_plan import (
    ACTION,
    ACTION_ADD,
    ACTION_ASIN,
    ACTION_BRAND_NO_DATA,
    ACTION_BRAND_OK,
    ACTION_CONQUEST,
    ACTION_DEFEND,
    ACTION_DO_NOT_ATTACK,
    ACTION_INVESTIGATE,
    ACTION_LOWER_BID,
    ACTION_MONITOR,
    ACTION_SCALE,
    BRAND_CVR,
    CAMPAIGN_COUNT,
    FUNNEL_BELOW_MARKET,
    FUNNEL_DIAGNOSIS,
    FUNNEL_LIKE_MARKET,
    FUNNEL_NO_DATA,
    IN_SEARCH_TERMS,
    MARKET_CVR,
    OPPORTUNITY_SCORE,
    QUERY,
    QUERY_TYPE,
    TERM_ACOS,
    TERM_ORDERS,
    TERM_SALES,
    TERM_SPEND,
    ActionPlanParams,
    accentless_text,
    build_action_plan,
    comma_terms,
    numeric_sqp,
    query_types,
    suggested_action,
    with_funnel_diagnosis,
)
from core.cross_analysis.ranking_guards import ALREADY_EXACT, NOT_NEGATABLE, RANKING_KEYWORD, with_ranking_guards
from core.search_term.frame import orders_column, sales_column
from tests.cross_analysis_data import search_terms, sqp, sqp_row, term_row

PARAMS = ActionPlanParams(target_acos=35.0, brand_terms=("luna",), competitors=("rival",),
                          catalog_asins=("b0own00001",))


def _query(text, *, query_type="Genérica", purchases=10, brand_purchases=1.0, brand_share=10.0, opportunity=0.0):
    return {"Search Query": text, "Tipo": query_type, "Purchases: Total Count": purchases,
            "Purchases: Brand Count": brand_purchases, "Purchases: Brand Share %": brand_share,
            "Opportunity Score": opportunity}


def _term(*, spend=10.0, sales=100.0, orders=3):
    return {TERM_SPEND: spend, TERM_SALES: sales, TERM_ORDERS: orders,
            TERM_ACOS: spend / sales * 100 if sales else math.nan}


@pytest.mark.parametrize("query", ["B0RIVAL001", "b0 rival 001", "compra b0own00001 hoy"])
def test_an_asin_query_or_one_of_the_catalog_is_a_product_target(query):
    assert suggested_action(_query(query), None, PARAMS) == ACTION_ASIN


def test_a_brand_query_that_names_a_competitor_is_conquest():
    assert suggested_action(_query("luna vs rival pajamas"), None, PARAMS) == ACTION_CONQUEST


def test_a_brand_query_without_its_purchase_share_has_no_data():
    assert suggested_action(_query("luna pajamas", brand_share=math.nan), None, PARAMS) == ACTION_BRAND_NO_DATA


@pytest.mark.parametrize("share, action", [(69.9, ACTION_DEFEND), (70.0, ACTION_BRAND_OK)])
def test_a_brand_query_is_defended_below_seventy_percent_of_its_purchases(share, action):
    assert suggested_action(_query("Luna Pajamas", brand_share=share), None, PARAMS) == action


def test_the_query_type_alone_makes_a_brand_query():
    assert suggested_action(_query("sleep sack", query_type="Marca", brand_share=20), None, PARAMS) == ACTION_DEFEND


def test_a_generic_query_that_runs_cheaply_with_confirmed_relevance_is_scaled():
    assert suggested_action(_query("sleep sack"), _term(spend=20, sales=100, orders=2), PARAMS) == ACTION_SCALE


def test_scaling_needs_positive_market_evidence_not_missing_data():
    query = _query("sleep sack", brand_purchases=math.nan, brand_share=math.nan)

    assert suggested_action(query, _term(spend=20, sales=100, orders=2), PARAMS) == ACTION_MONITOR


def test_a_query_the_brand_sells_by_and_no_campaign_captures_is_added():
    assert suggested_action(_query("sleep sack", brand_purchases=2), None, PARAMS) == ACTION_ADD


def test_a_big_market_the_brand_never_sells_in_is_not_attacked():
    query = _query("sleep sack", purchases=501, brand_purchases=0, brand_share=0.0)

    assert suggested_action(query, None, PARAMS) == ACTION_DO_NOT_ATTACK


def test_a_high_opportunity_with_a_low_share_and_few_purchases_is_investigated():
    query = _query("sleep sack", purchases=100, brand_purchases=0, brand_share=2.0, opportunity=41)

    assert suggested_action(query, None, PARAMS) == ACTION_INVESTIGATE


def test_spend_without_sales_lowers_the_bid_before_the_acos_rule():
    query = _query("sleep sack", brand_purchases=0, brand_share=0.0)

    assert suggested_action(query, _term(spend=12, sales=0, orders=0), PARAMS) == ACTION_LOWER_BID


def test_an_acos_over_twice_the_target_lowers_the_bid():
    assert suggested_action(_query("sleep sack"), _term(spend=80, sales=100, orders=1), PARAMS) == ACTION_LOWER_BID


def test_anything_else_is_monitored():
    assert suggested_action(_query("sleep sack"), _term(spend=40, sales=100, orders=1), PARAMS) == ACTION_MONITOR


def _plan(queries, terms, exact=frozenset(), params=PARAMS):
    table = sqp(*queries)
    table[QUERY_TYPE] = query_types(table[QUERY], params.brand_terms)
    guarded = with_ranking_guards(search_terms(*terms), exact)
    return build_action_plan(with_funnel_diagnosis(numeric_sqp(table)), guarded, exact, params,
                             sales_column=sales_column(7), orders_column=orders_column(7))


def test_the_plan_scores_opportunity_from_0_to_100_so_a_big_query_the_brand_barely_sells_is_investigated():
    plan = _plan([sqp_row("sleep sack", impressions=10000, clicks=1000, purchases=100, brand_purchases=0,
                          brand_share=0.0),
                  sqp_row("cozy blanket", impressions=100, clicks=10, purchases=5, brand_purchases=0,
                          brand_share=0.0)], [])

    assert dict(zip(plan[QUERY], plan[OPPORTUNITY_SCORE])) == {"sleep sack": 70.0, "cozy blanket": 0.0}
    assert dict(zip(plan[QUERY], plan[ACTION])) == {"sleep sack": ACTION_INVESTIGATE, "cozy blanket": ACTION_MONITOR}


def test_the_plan_has_each_query_once_with_its_volumes_added_up():
    plan = _plan([sqp_row("sleep sack", purchases=10, brand_share=10.0), sqp_row("sleep sack", purchases=5,
                                                                                  brand_share=30.0)], [])

    assert list(plan[QUERY]) == ["sleep sack"]
    row = plan.iloc[0]
    assert (row["Purchases: Total Count"], row["Purchases: Brand Share %"]) == (15, 20.0)


def test_a_query_takes_the_ids_and_marks_of_its_top_spend_campaign():
    plan = _plan([sqp_row("sleep sack", brand_purchases=0, brand_share=0.0)],
                 [term_row("sleep sack", campaign_id="3001", ad_group_id="4001", keyword_id="5001", cost=4.0),
                  term_row("sleep sack", campaign_id="3002", ad_group_id="4002", keyword_id="5002", cost=9.0,
                           keyword_type="EXACT", portfolio="Ranking", portfolio_id="9")])

    row = plan.iloc[0]
    assert (row["_campaign_id"], row["_ad_group_id"], row["_keyword_id"]) == ("3002", "4002", "5002")
    assert (row[NOT_NEGATABLE], row[RANKING_KEYWORD], row[CAMPAIGN_COUNT]) == (True, True, 2)
    assert (row[TERM_SPEND], row[IN_SEARCH_TERMS]) == (13.0, "✅ Sí")
    assert row[ACTION] == ACTION_LOWER_BID


def test_a_query_no_campaign_captures_has_no_ids_and_no_marks():
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2)], [term_row("sleep sack")])

    row = plan.iloc[0]
    assert (row[ACTION], row[IN_SEARCH_TERMS]) == (ACTION_ADD, "❌ No")
    assert pd.isna(row["_campaign_id"])
    assert (row[NOT_NEGATABLE], row[RANKING_KEYWORD]) == (False, False)


def test_a_query_that_exists_as_an_enabled_exact_is_marked_even_without_a_click():
    # The report never saw "baby swaddle", so only the listing knows it already runs as an exact keyword.
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2), sqp_row("sleep sack")], [term_row("sleep sack")],
                 exact=frozenset({"baby swaddle"}))

    assert dict(zip(plan[QUERY], plan[ALREADY_EXACT])) == {"baby swaddle": True, "sleep sack": False}


def test_without_a_listing_the_exact_mark_of_every_query_is_unknown():
    plan = _plan([sqp_row("baby swaddle")], [], exact=None)

    assert plan[ALREADY_EXACT].isna().all()


def test_the_funnel_diagnosis_compares_the_brands_conversion_with_the_markets():
    table = with_funnel_diagnosis(numeric_sqp(sqp(
        sqp_row("like market", clicks=100, purchases=10, brand_clicks=10, brand_purchases=1),
        sqp_row("below market", clicks=100, purchases=10, brand_clicks=10, brand_purchases=0.5),
        sqp_row("no brand clicks", clicks=100, purchases=10, brand_clicks=0, brand_purchases=0),
    )))

    assert list(table[FUNNEL_DIAGNOSIS]) == [FUNNEL_LIKE_MARKET, FUNNEL_BELOW_MARKET, FUNNEL_NO_DATA]
    assert list(table[MARKET_CVR]) == [10.0, 10.0, 10.0]
    assert table[BRAND_CVR].tolist()[:2] == [10.0, 5.0]


def test_without_the_brand_counts_there_is_no_funnel_diagnosis():
    table = with_funnel_diagnosis(numeric_sqp(pd.DataFrame(
        {"Search Query": ["sleep sack"], "Clicks: Total Count": [100], "Purchases: Total Count": [10]})))

    assert FUNNEL_DIAGNOSIS not in table.columns
    assert list(table[MARKET_CVR]) == [10.0]


def test_brand_terms_are_matched_without_accents_or_case():
    types = query_types(pd.Series(["Crema LUNA  bebé", "sleep sack", None]), comma_terms(" Luna , , Dermaglós"))

    assert list(types) == ["Marca", "Genérica", "Genérica"]
    assert accentless_text("  Dermaglós   Crema ") == "dermaglos crema"

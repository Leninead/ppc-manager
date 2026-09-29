"""The two files the Plan de Acción exports: the Amazon bulk and the plan Campaign Builder reads. No network."""
import io
import math

import pandas as pd

from core.bulk.export import build_bid_update, build_keyword_create
from core.cross_analysis.action_plan import (
    ACTION_ADD,
    ACTION_DEFEND,
    ACTION_LOWER_BID,
    ACTION_MONITOR,
    ACTION_SCALE,
    ActionPlanParams,
    QUERY,
    QUERY_TYPE,
    build_action_plan,
    numeric_sqp,
    query_types,
)
from core.cross_analysis.plan_exports import (
    ALREADY_EXACT_IN_ACCOUNT,
    CB_ACTION,
    CB_CONTRACT_COLUMNS,
    CB_KEYWORD,
    CB_REASON,
    NOT_IN_CAMPAIGN_BUILDER,
    bulk_rows,
    campaign_builder_plan,
)
from core.cross_analysis.ranking_guards import ALREADY_EXACT, with_ranking_guards
from core.search_term.frame import orders_column, sales_column
from tests.cross_analysis_data import search_terms, sqp, sqp_row, term_row

PARAMS = ActionPlanParams(target_acos=35.0, brand_terms=("luna",))


def _plan(queries, terms, exact=frozenset()):
    table = sqp(*queries)
    table[QUERY_TYPE] = query_types(table[QUERY], PARAMS.brand_terms)
    return build_action_plan(numeric_sqp(table), with_ranking_guards(search_terms(*terms), exact), exact, PARAMS,
                             sales_column=sales_column(7), orders_column=orders_column(7))


def test_bid_updates_point_at_the_keyword_the_term_came_through_with_its_text_and_match_type():
    plan = _plan([sqp_row("sleep sack winter", brand_purchases=0, brand_share=0.0)],
                 [term_row("sleep sack winter", keyword_type="PHRASE", keyword_id="5009", keyword_text="sleep sack",
                           campaign_id="3009", ad_group_id="4009", cost=12.0)])

    rows = bulk_rows(plan, 0.5)

    assert rows.creates == []
    assert rows.updates == [{"campaign_id": "3009", "ad_group_id": "4009", "campaign_name": "Luna - SP - 3009",
                             "ad_group_name": "AG 4009", "keyword_text": "sleep sack", "bid": 0.5,
                             "keyword_id": "5009", "match_type": "Phrase"}]


def test_two_terms_that_came_through_the_same_keyword_update_it_once():
    plan = _plan([sqp_row("sleep sack winter", brand_purchases=0, brand_share=0.0),
                  sqp_row("sleep sack cotton", brand_purchases=0, brand_share=0.0)],
                 [term_row("sleep sack winter", keyword_id="5010", keyword_text="sleep sack", cost=12.0),
                  term_row("sleep sack cotton", keyword_id="5010", keyword_text="sleep sack", cost=8.0)])

    rows = bulk_rows(plan, 0.5)
    bulk, invalid = build_bid_update(rows.updates)

    assert list(zip(bulk["Keyword ID"], bulk["Keyword Text"])) == [("5010", "sleep sack")]
    assert invalid.empty
    assert rows.same_keyword == ["sleep sack winter"]


def test_an_auto_or_product_target_term_carries_no_keyword_id_and_the_builder_rejects_it():
    plan = _plan([sqp_row("cozy blanket", brand_purchases=0, brand_share=0.0),
                  sqp_row("b0rival0001", brand_purchases=0, brand_share=0.0)],
                 [term_row("cozy blanket", keyword_type="TARGETING_EXPRESSION_PREDEFINED", keyword_id="7002",
                           keyword_text="close-match", cost=12.0)])

    rows = bulk_rows(plan, 0.5)
    _, invalid = build_bid_update(rows.updates)

    assert [(row["keyword_text"], row["keyword_id"]) for row in rows.updates] == [("cozy blanket", "")]
    assert len(invalid) == 1


def test_a_brand_query_to_defend_is_created_in_its_top_spend_ad_group_as_exact():
    plan = _plan([sqp_row("luna pajamas", brand_share=40.0)], [term_row("luna pajamas", keyword_type="BROAD")])

    rows = bulk_rows(plan, 0.5)

    assert [(row["keyword_text"], row["match_type"], row["ad_group_id"]) for row in rows.creates] == [
        ("luna pajamas", "Exact", "4001")]
    bulk, invalid = build_keyword_create(rows.creates)
    assert (len(bulk), len(invalid)) == (1, 0)


def test_a_keyword_the_account_already_has_as_an_enabled_exact_is_never_created_again():
    plan = _plan([sqp_row("luna pajamas", brand_share=40.0)],
                 [term_row("luna pajamas", keyword_type="EXACT")], exact=frozenset({"luna pajamas"}))

    rows = bulk_rows(plan, 0.5)

    assert (rows.creates, rows.already_exact) == ([], ["luna pajamas"])


def test_without_a_listing_the_create_goes_out_since_nothing_says_it_exists():
    plan = _plan([sqp_row("luna pajamas", brand_share=40.0)], [term_row("luna pajamas")], exact=None)

    rows = bulk_rows(plan, 0.5)

    assert [row["keyword_text"] for row in rows.creates] == ["luna pajamas"]
    assert rows.already_exact == []


def test_a_query_to_add_has_no_ids_and_stays_an_invalid_create():
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2)], [])

    rows = bulk_rows(plan, 0.5)
    _, invalid = build_keyword_create(rows.creates)

    assert [(row["keyword_text"], row["match_type"], row["campaign_id"]) for row in rows.creates] == [
        ("baby swaddle", "Phrase", "")]
    assert len(invalid) == 1


def test_the_campaign_builder_plan_starts_with_its_contract_columns_and_its_three_actions():
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2, purchases=60, brand_share=6.7),
                  sqp_row("luna pajamas", brand_share=40.0), sqp_row("sleep sack", brand_purchases=0, brand_share=0.0),
                  sqp_row("quiet query", purchases=3, brand_purchases=0, brand_share=math.nan)],
                 [term_row("luna pajamas"), term_row("sleep sack", campaign_id="3002", cost=12.0)])

    builder = campaign_builder_plan(plan)

    assert list(builder.rows.columns[:4]) == list(CB_CONTRACT_COLUMNS)
    assert dict(zip(builder.rows[CB_KEYWORD], builder.rows[CB_ACTION])) == {"baby swaddle": ACTION_ADD,
                                                                           "luna pajamas": ACTION_DEFEND}
    assert builder.rows.loc[builder.rows[CB_KEYWORD] == "baby swaddle", "Purchases mercado"].item() == 60
    assert dict(zip(builder.left_out[CB_KEYWORD], builder.left_out[CB_REASON])) == {
        "sleep sack": NOT_IN_CAMPAIGN_BUILDER, "quiet query": NOT_IN_CAMPAIGN_BUILDER}
    assert builder.exact_checked


def test_the_campaign_builder_plan_leaves_out_what_already_exists_as_an_enabled_exact():
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2), sqp_row("luna pajamas", brand_share=40.0)],
                 [term_row("luna pajamas")], exact=frozenset({"baby swaddle"}))

    builder = campaign_builder_plan(plan)

    assert list(builder.rows[CB_KEYWORD]) == ["luna pajamas"]
    assert dict(zip(builder.left_out[CB_KEYWORD], builder.left_out[CB_REASON])) == {
        "baby swaddle": ALREADY_EXACT_IN_ACCOUNT}


def test_without_a_listing_the_campaign_builder_plan_says_it_could_not_check_duplicates():
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2)], [], exact=None)

    builder = campaign_builder_plan(plan)

    assert list(builder.rows[CB_KEYWORD]) == ["baby swaddle"]
    assert not builder.exact_checked


def test_campaign_builder_reads_the_plan_the_way_it_reads_its_first_sheet():
    plan = _plan([sqp_row("baby swaddle", brand_purchases=2), sqp_row("luna pajamas", brand_share=40.0)],
                 [term_row("luna pajamas")])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        campaign_builder_plan(plan).rows.to_excel(writer, sheet_name="Plan de Acción", index=False)

    read_back = pd.read_excel(io.BytesIO(buffer.getvalue()))

    assert "Keyword" in read_back.columns
    wanted = read_back[read_back["Acción sugerida"].isin([ACTION_SCALE, ACTION_ADD, ACTION_DEFEND])]
    assert sorted(wanted["Keyword"]) == ["baby swaddle", "luna pajamas"]


def test_only_the_bulk_actions_become_rows():
    plan = _plan([sqp_row("quiet query", purchases=3, brand_purchases=0, brand_share=math.nan)], [])

    rows = bulk_rows(plan, 0.5)

    assert plan[ALREADY_EXACT].notna().all()
    assert plan["Acción"].tolist() == [ACTION_MONITOR]
    assert (rows.creates, rows.updates) == ([], [])
    assert ACTION_LOWER_BID not in plan["Acción"].tolist()

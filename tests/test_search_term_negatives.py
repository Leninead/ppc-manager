"""Negatives mining rules and bulk selection over synthetic search term frames. No network."""
from __future__ import annotations

import csv
import io
from datetime import date

import pandas as pd
import pytest

from core.amazon_ads.report_provider import ProfileOption, ReportProvider
from core.bulk_export import build_adgroup_negative
from core.search_term_frame import ANY_WINDOW_PURCHASES, HIDDEN_ID_COLUMNS, PORTFOLIO_NAME_MISSING, add_ratios
from core.search_term_negatives import (
    ACTION_LOWER_BID,
    ACTION_NEGATIVE,
    ACTION_REVIEW,
    AD_GROUP_STATE_UNVERIFIED_NOTE,
    EXACT_GUARD_PARTIAL_NOTE,
    EXCLUDED_ACTIVE_EXACT,
    EXCLUDED_CONVERTS,
    EXCLUDED_DUPLICATE,
    EXCLUDED_EXACT_ORIGIN,
    EXCLUDED_MISSING_IDS,
    EXCLUDED_NOT_A_QUERY,
    EXCLUDED_OWN_KEYWORD,
    EXCLUDED_PHRASE_BLOCKS,
    EXCLUDED_PRODUCT_TARGETING_ORIGIN,
    EXCLUDED_UNKNOWN_ORIGIN,
    NEGATIVE_EXACT,
    NEGATIVE_PHRASE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_REVIEW,
    RULE_EXTREME_ACOS,
    RULE_FEW_CLICKS,
    RULE_LOW_CTR,
    RULE_NO_CONVERSION_CLICKS,
    RULE_NO_CONVERSION_SPEND,
    NegativeCandidate,
    evaluate_candidates,
    negative_key,
    select_for_bulk,
)
from modules.pages.search_term_report import _detect_cols

CLICKS_THRESHOLD = 20
SPEND_THRESHOLD = 15.0

_COLUMN_BY_FIELD = {
    "term": "Customer Search Term", "campaign": "Campaign Name", "ad_group": "Ad Group Name",
    "portfolio": "Portfolio name", "match_type": "Match Type", "targeting": "Targeting",
    "impressions": "Impressions", "clicks": "Clicks", "spend": "Spend", "sales": "7 Day Total Sales",
    "orders": "7 Day Total Orders (#)", "units": "7 Day Total Units (#)",
    "campaign_id": "_campaign_id", "ad_group_id": "_ad_group_id", "keyword_id": "_keyword_id",
    "keyword_type": "_keyword_type", "origin": "_origin_match_type", "status": "_campaign_status",
    "keyword_status": "_ad_keyword_status", "keyword_text": "_keyword_text",
    "any_window_purchases": ANY_WINDOW_PURCHASES, "portfolio_name_missing": PORTFOLIO_NAME_MISSING,
}
_DEFAULTS = {
    "term": "jabon neutro bebe", "campaign": "Demo - SP - KW - BROAD", "ad_group": "Grupo Demo",
    "portfolio": "DISCOVERY", "match_type": "BROAD", "targeting": "jabon neutro", "impressions": 800,
    "clicks": 5, "spend": 2.0, "sales": 0.0, "orders": 0, "units": 0, "campaign_id": "300000000000001",
    "ad_group_id": "400000000000001", "keyword_id": "500000000000001", "keyword_type": "BROAD", "origin": "BROAD",
    "status": "ENABLED", "keyword_status": "ENABLED", "keyword_text": "jabon neutro",
    "portfolio_name_missing": False,
}


def _row(**fields) -> dict:
    values = {**_DEFAULTS, **fields}
    values.setdefault("any_window_purchases", values["orders"])
    return {_COLUMN_BY_FIELD[field]: value for field, value in values.items()}


def _frame(*rows: dict) -> pd.DataFrame:
    return add_ratios(pd.DataFrame(list(rows)), 7)


def _candidates(frame: pd.DataFrame) -> list[NegativeCandidate]:
    return evaluate_candidates(frame, _detect_cols(frame), clicks_threshold=CLICKS_THRESHOLD,
                               spend_threshold=SPEND_THRESHOLD)


def _only(frame: pd.DataFrame) -> NegativeCandidate:
    candidates = _candidates(frame)
    assert len(candidates) == 1
    return candidates[0]


def _select(frame: pd.DataFrame, **options):
    return select_for_bulk(_candidates(frame), frame, **options)


def test_r2_clicks_without_orders_is_a_high_priority_negative_exact():
    candidate = _only(_frame(_row(clicks=25, spend=5.0)))

    assert (candidate.rule, candidate.action, candidate.match_type, candidate.priority) == (
        RULE_NO_CONVERSION_CLICKS, ACTION_NEGATIVE, NEGATIVE_EXACT, PRIORITY_HIGH)


def test_r3_spend_without_orders_is_a_high_priority_negative_exact():
    candidate = _only(_frame(_row(clicks=5, spend=16.0)))

    assert (candidate.rule, candidate.action, candidate.match_type, candidate.priority) == (
        RULE_NO_CONVERSION_SPEND, ACTION_NEGATIVE, NEGATIVE_EXACT, PRIORITY_HIGH)


def test_r5_low_ctr_is_a_medium_priority_negative_phrase():
    candidate = _only(_frame(_row(impressions=3000, clicks=4, spend=2.0)))

    assert (candidate.rule, candidate.action, candidate.match_type, candidate.priority) == (
        RULE_LOW_CTR, ACTION_NEGATIVE, NEGATIVE_PHRASE, PRIORITY_MEDIUM)


@pytest.mark.parametrize("fields, rule", [
    ({"clicks": 25, "spend": 20.0, "impressions": 20000}, RULE_NO_CONVERSION_CLICKS),
    ({"clicks": 5, "spend": 20.0, "impressions": 5000}, RULE_NO_CONVERSION_SPEND),
])
def test_first_matching_rule_wins_in_m2_order(fields, rule):
    assert _only(_frame(_row(**fields))).rule == rule


def test_r4_extreme_acos_lowers_the_bid_and_is_never_a_negative():
    candidate = _only(_frame(_row(orders=2, sales=10.0, spend=8.0, clicks=30)))

    assert candidate.rule == RULE_EXTREME_ACOS
    assert candidate.action == ACTION_LOWER_BID
    assert candidate.match_type == ""
    assert candidate.priority == PRIORITY_MEDIUM
    assert candidate.acos == 80.0


def test_r4_does_not_apply_from_five_orders():
    assert _candidates(_frame(_row(orders=5, sales=10.0, spend=8.0, clicks=30))) == []


def test_r1_few_clicks_goes_to_manual_review_and_is_never_a_negative():
    candidate = _only(_frame(_row(clicks=3, spend=1.0)))

    assert candidate.rule == RULE_FEW_CLICKS
    assert candidate.action == ACTION_REVIEW
    assert candidate.priority == PRIORITY_REVIEW
    assert candidate.match_type == NEGATIVE_EXACT


@pytest.mark.parametrize("orders", [1, 2, 4, 5, 12])
def test_a_term_with_orders_is_never_a_negative(orders):
    frame = _frame(_row(orders=orders, sales=1.0, spend=900.0, clicks=500, impressions=1_000_000))

    assert all(candidate.action != ACTION_NEGATIVE for candidate in _candidates(frame))


def test_rows_without_clicks_or_orders_are_not_candidates():
    assert _candidates(_frame(_row(clicks=0, spend=0.0, impressions=100))) == []


def test_every_suggested_negative_match_type_is_title_case():
    candidates = _candidates(_frame(
        _row(term="a", clicks=25), _row(term="b", spend=16.0), _row(term="c", impressions=3000, clicks=4),
        _row(term="d", clicks=2), _row(term="e", orders=1, sales=5.0, spend=9.0),
    ))

    assert {candidate.match_type for candidate in candidates} == {NEGATIVE_EXACT, NEGATIVE_PHRASE, ""}
    assert {candidate.match_type for candidate in candidates if candidate.action == ACTION_NEGATIVE} == {
        "Negative Exact", "Negative Phrase"}


def test_candidates_are_sorted_by_priority_then_spend():
    candidates = _candidates(_frame(
        _row(term="revisar", clicks=2, spend=9.0),
        _row(term="alta barata", clicks=25, spend=3.0),
        _row(term="media", impressions=3000, clicks=4, spend=14.0),
        _row(term="alta cara", clicks=30, spend=40.0),
    ))

    assert [candidate.search_term for candidate in candidates] == ["alta cara", "alta barata", "media", "revisar"]


def test_acos_is_none_without_orders():
    assert _only(_frame(_row(clicks=25))).acos is None


def test_ids_status_origin_and_portfolio_are_copied_from_the_frame():
    candidate = _only(_frame(_row(clicks=25, origin="auto", status="ENABLED", portfolio="RANKING Core")))

    assert (candidate.campaign_id, candidate.ad_group_id) == ("300000000000001", "400000000000001")
    assert candidate.origin_match_type == "AUTO"
    assert candidate.campaign_status == "ENABLED"
    assert candidate.portfolio == "RANKING Core"
    assert (candidate.campaign, candidate.ad_group) == ("Demo - SP - KW - BROAD", "Grupo Demo")


def test_a_file_frame_without_hidden_columns_gives_empty_ids():
    frame = _frame(_row(clicks=25)).drop(columns=list(HIDDEN_ID_COLUMNS))

    candidate = _only(frame)

    assert (candidate.campaign_id, candidate.ad_group_id, candidate.origin_match_type) == ("", "", "")


def test_console_text_numbers_are_read_like_m2():
    frame = _frame(_row(clicks=5))
    frame["Spend"] = "$1,016.00"

    assert _only(frame).rule == RULE_NO_CONVERSION_SPEND
    assert _only(frame).spend == 1016.0


def test_frame_without_search_term_column_is_rejected():
    frame = _frame(_row(clicks=25)).drop(columns=["Customer Search Term"])

    with pytest.raises(ValueError, match="search term"):
        evaluate_candidates(frame, _detect_cols(frame), clicks_threshold=CLICKS_THRESHOLD,
                            spend_threshold=SPEND_THRESHOLD)


def test_bulk_rows_have_the_build_adgroup_negative_shape():
    rows, exclusions = _select(_frame(_row(clicks=25)))

    assert exclusions == []
    assert rows == [{
        "campaign_id": "300000000000001", "ad_group_id": "400000000000001", "keyword_text": "jabon neutro bebe",
        "match_type": "Negative Exact", "campaign_name": "Demo - SP - KW - BROAD", "ad_group_name": "Grupo Demo",
    }]


def test_only_negativo_candidates_reach_the_bulk_or_the_exclusions():
    rows, exclusions = _select(_frame(
        _row(term="revisar", clicks=2), _row(term="bajar bid", orders=1, sales=5.0, spend=9.0),
    ))

    assert (rows, exclusions) == ([], [])


@pytest.mark.parametrize("origin, reason", [
    ("EXACT", EXCLUDED_EXACT_ORIGIN),
    ("PRODUCT_TARGETING", EXCLUDED_PRODUCT_TARGETING_ORIGIN),
    ("", EXCLUDED_UNKNOWN_ORIGIN),
])
def test_terms_from_exact_product_targeting_or_unknown_origin_are_excluded(origin, reason):
    rows, exclusions = _select(_frame(_row(clicks=25, origin=origin)))

    assert rows == []
    assert [exclusion.reason for exclusion in exclusions] == [reason]


@pytest.mark.parametrize("origin", ["BROAD", "PHRASE", "AUTO"])
def test_terms_from_broad_phrase_or_auto_are_bulk_eligible(origin):
    rows, _ = _select(_frame(_row(clicks=25, origin=origin)))

    assert len(rows) == 1


def test_campaigns_that_are_not_enabled_are_excluded():
    rows, exclusions = _select(_frame(
        _row(term="pausada", clicks=25, status="PAUSED"), _row(term="activa", clicks=25, status="enabled"),
    ))

    assert [row["keyword_text"] for row in rows] == ["activa"]
    assert "no está activa" in exclusions[0].reason and "PAUSED" in exclusions[0].reason


@pytest.mark.parametrize("term", ["*", "B0ABCDEFGH", "b0abc12345"])
def test_asins_and_the_wildcard_are_excluded(term):
    rows, exclusions = _select(_frame(_row(term=term, clicks=25)))

    assert rows == []
    assert exclusions[0].reason == EXCLUDED_NOT_A_QUERY


@pytest.mark.parametrize("term", ["b0 jabon", "b0abcdefg", "b0abcdefghi"])
def test_terms_that_only_resemble_an_asin_stay_eligible(term):
    rows, _ = _select(_frame(_row(term=term, clicks=25)))

    assert len(rows) == 1


def _exact_keyword_row(keyword_status: str) -> dict:
    return _row(term="jabon neutro bebe", campaign="Demo - SP - KW - EXACT", campaign_id="300000000000002",
                ad_group_id="400000000000002", keyword_id="500000000000002", keyword_type="EXACT", origin="EXACT",
                match_type="EXACT", keyword_status=keyword_status, keyword_text="Jabon  Neutro Bebe", clicks=2)


def test_a_term_running_as_an_active_exact_keyword_is_excluded():
    rows, exclusions = _select(_frame(_row(clicks=25), _exact_keyword_row("ENABLED")))

    assert rows == []
    assert [exclusion.reason for exclusion in exclusions] == [EXCLUDED_ACTIVE_EXACT]


def test_a_paused_exact_keyword_does_not_protect_the_term():
    rows, _ = _select(_frame(_row(clicks=25), _exact_keyword_row("PAUSED")))

    assert len(rows) == 1


def test_ranking_portfolios_are_excluded_by_default_and_included_on_request():
    frame = _frame(_row(clicks=25, portfolio="Ranking - Core"))

    rows, exclusions = _select(frame)
    rows_opted_in, exclusions_opted_in = _select(frame, released_ranking=frozenset({
        negative_key(exclusions[0].candidate)}))

    assert rows == []
    assert "RANKING" in exclusions[0].reason and "Ranking - Core" in exclusions[0].reason
    assert len(rows_opted_in) == 1 and exclusions_opted_in == []


@pytest.mark.parametrize("ids", [{"campaign_id": ""}, {"ad_group_id": " "}])
def test_candidates_without_ids_are_excluded(ids):
    rows, exclusions = _select(_frame(_row(clicks=25, **ids)))

    assert rows == []
    assert exclusions[0].reason == EXCLUDED_MISSING_IDS


def test_a_term_converting_in_the_same_ad_group_through_another_target_is_excluded():
    rows, exclusions = _select(_frame(
        _row(clicks=25),
        _row(term="Jabon Neutro Bebe", keyword_id="500000000000009", targeting="jabon", orders=1, sales=30.0),
    ))

    assert rows == []
    assert [exclusion.reason for exclusion in exclusions] == [EXCLUDED_CONVERTS]


def test_a_term_converting_only_in_another_ad_group_stays_eligible():
    rows, _ = _select(_frame(
        _row(clicks=25),
        _row(ad_group_id="400000000000009", keyword_id="500000000000009", orders=1, sales=30.0),
    ))

    assert len(rows) == 1


def test_a_handmade_negative_candidate_with_orders_is_excluded():
    frame = _frame(_row(clicks=25))
    candidate = _only(frame)
    with_orders = NegativeCandidate(**{**candidate.__dict__, "orders": 2})

    rows, exclusions = select_for_bulk([with_orders], frame)

    assert rows == []
    assert exclusions[0].reason == EXCLUDED_CONVERTS


def test_duplicate_negatives_are_deduplicated_per_ad_group_term_and_match_type():
    rows, exclusions = _select(_frame(
        _row(clicks=25, spend=9.0),
        _row(term=" Jabon  NEUTRO bebe", keyword_id="500000000000003", clicks=30, spend=8.0),
        _row(keyword_id="500000000000004", impressions=3000, clicks=4, spend=1.0),
    ))

    assert sorted(row["match_type"] for row in rows) == ["Negative Exact", "Negative Phrase"]
    assert [exclusion.reason for exclusion in exclusions] == [EXCLUDED_DUPLICATE]


def test_selection_requires_a_bulk_ready_frame():
    frame = _frame(_row(clicks=25)).drop(columns=list(HIDDEN_ID_COLUMNS))

    with pytest.raises(ValueError, match="bulk-ready"):
        select_for_bulk(_candidates(frame), frame)


def test_selected_rows_pass_build_adgroup_negative_without_invalid_rows():
    frame = _frame(
        _row(term="jabon barato", clicks=25),
        _row(term="shampoo perro", spend=16.0, ad_group_id="400000000000007"),
        _row(term="crema solar", impressions=4000, clicks=5, origin="AUTO", match_type="-"),
        _row(term="jabon de lavanda", clicks=40, origin="PHRASE", campaign_id="300000000000005"),
        _row(term="B0ABCDEFGH", clicks=40),
        _row(term="con ventas", orders=1, sales=5.0, spend=9.0),
    )

    rows, exclusions = _select(frame)
    bulk, invalid = build_adgroup_negative(rows)

    assert len(rows) == 4 and len(exclusions) == 1
    assert invalid.empty
    assert len(bulk) == 4
    assert set(bulk["Entity"]) == {"Negative Keyword"}
    assert set(bulk["Match Type"]) == {"Negative Exact", "Negative Phrase"}


class _FakeRest:
    def __init__(self, csv_bytes: bytes):
        self._csv_bytes = csv_bytes

    def rpc_csv(self, name, args, *, timeout_s=8):
        return self._csv_bytes


def _api_csv(rows: list[dict]) -> bytes:
    base = {
        "campaign_id": "300000000000001", "ad_group_id": "400000000000001", "keyword_type": "BROAD",
        "keyword_id": "500000000000001", "match_type": "BROAD", "targeting": "jabon", "search_term": "jabon",
        "campaign_name": "Demo - SP - KW - BROAD", "campaign_status": "ENABLED", "ad_group_name": "Grupo Demo",
        "keyword_text": "jabon", "ad_keyword_status": "ENABLED", "portfolio_id": "", "portfolio_name": "",
        "impressions": "900", "clicks": "30", "cost": "12.5", "purchases_7d": "0", "sales_7d": "0", "units_7d": "0",
        "purchases_14d": "0", "sales_14d": "0", "units_14d": "0", "currency_code": "MXN",
    }
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(base), lineterminator="\n")
    writer.writeheader()
    writer.writerows({**base, **row} for row in rows)
    return buffer.getvalue().encode("utf-8")


def test_provider_frame_flows_into_a_valid_negative_bulk():
    option = ProfileOption.from_row({"profile_id": "1111222233334444", "cliente": "Marca Demo", "country_code": "MX",
                                     "account_type": "seller", "status": "active"})
    csv_bytes = _api_csv([
        {"search_term": "jabon sin aroma"},
        {"search_term": "jabon exacto", "keyword_type": "EXACT", "match_type": "EXACT", "keyword_text": "jabon exacto"},
        {"search_term": "b0abcdefgh", "keyword_type": "TARGETING_EXPRESSION_PREDEFINED",
         "match_type": "TARGETING_EXPRESSION_PREDEFINED", "keyword_text": "", "targeting": "substitutes"},
        {"search_term": "jabon liquido", "keyword_type": "TARGETING_EXPRESSION_PREDEFINED",
         "match_type": "TARGETING_EXPRESSION_PREDEFINED", "keyword_text": "", "targeting": "close-match"},
    ])
    source = ReportProvider(_FakeRest(csv_bytes)).search_terms(option, date(2026, 8, 31), date(2026, 9, 13))

    candidates = evaluate_candidates(source.frame, _detect_cols(source.frame), clicks_threshold=CLICKS_THRESHOLD,
                                     spend_threshold=SPEND_THRESHOLD)
    rows, exclusions = select_for_bulk(candidates, source.frame)
    bulk, invalid = build_adgroup_negative(rows)

    assert sorted(row["keyword_text"] for row in rows) == ["jabon liquido", "jabon sin aroma"]
    assert sorted(exclusion.reason for exclusion in exclusions) == sorted([EXCLUDED_EXACT_ORIGIN,
                                                                           EXCLUDED_NOT_A_QUERY])
    assert invalid.empty and len(bulk) == 2


def test_exact_guard_note_is_one_spanish_sentence():
    assert EXACT_GUARD_PARTIAL_NOTE.endswith(".")
    assert EXACT_GUARD_PARTIAL_NOTE.count(". ") == 0
    assert "Exact" in EXACT_GUARD_PARTIAL_NOTE and "clicks" in EXACT_GUARD_PARTIAL_NOTE


def test_ad_group_state_note_is_one_spanish_sentence():
    assert AD_GROUP_STATE_UNVERIFIED_NOTE.endswith(".")
    assert AD_GROUP_STATE_UNVERIFIED_NOTE.count(". ") == 0
    assert "ad group" in AD_GROUP_STATE_UNVERIFIED_NOTE


def _reasons(exclusions) -> list[str]:
    return [exclusion.reason for exclusion in exclusions]


# Negative Phrase must not block what converts in its ad group (INV-2)

def _low_ctr_row(term: str, **fields) -> dict:
    return _row(**{"term": term, "impressions": 3000, "clicks": 3, "spend": 2.5, "keyword_text": "sleeping bag",
                   "targeting": "sleeping bag", **fields})


def _converting_row(term: str, **fields) -> dict:
    return _row(**{"term": term, "impressions": 900, "clicks": 40, "spend": 30.0, "orders": 10, "sales": 300.0,
                   "units": 10, "keyword_id": "500000000000002", "keyword_text": "sleeping bag",
                   "targeting": "sleeping bag", **fields})


@pytest.mark.parametrize("phrase, converting", [
    ("baby sleeping bag", "baby sleeping bag 2.5 tog"),
    ("baby sleeping bags", "warm baby sleeping bag 2.5 tog"),
    ("sleeping bag", "Baby Sleeping Bags"),
    ("boxes", "toy box"),
])
def test_a_phrase_negative_that_would_block_a_converting_term_of_its_ad_group_is_excluded(phrase, converting):
    rows, exclusions = _select(_frame(_low_ctr_row(phrase), _converting_row(converting)))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_PHRASE_BLOCKS]
    assert exclusions[0].candidate.match_type == NEGATIVE_PHRASE


def test_a_one_word_auto_phrase_negative_that_would_block_converting_queries_is_excluded():
    auto = {"origin": "AUTO", "keyword_type": "TARGETING_EXPRESSION_PREDEFINED", "match_type": "-",
            "keyword_text": "close-match", "targeting": "close-match"}
    rows, exclusions = _select(_frame(
        _row(term="bag", impressions=5000, clicks=5, spend=4.0, **auto),
        _row(term="baby sleeping bag", impressions=1200, clicks=30, spend=25.0, orders=8, sales=240.0, units=8,
             keyword_id="500000000000002", **auto),
    ))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_PHRASE_BLOCKS]


def test_a_phrase_negative_inside_an_enabled_exact_keyword_of_its_ad_group_is_excluded():
    rows, exclusions = _select(_frame(
        _low_ctr_row("sleeping bag", keyword_text="kids bag"),
        _row(term="kids sleeping bag", keyword_id="500000000000002", keyword_type="EXACT", origin="EXACT",
             match_type="EXACT", keyword_text="kids sleeping bag", targeting="kids sleeping bag", clicks=2),
    ))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_PHRASE_BLOCKS]


def test_a_phrase_negative_only_blocking_terms_of_another_ad_group_stays_eligible():
    rows, exclusions = _select(_frame(
        _low_ctr_row("baby sleeping bag", keyword_text="kids bag"),
        _converting_row("baby sleeping bag 2.5 tog", ad_group_id="400000000000009"),
    ))

    assert [row["keyword_text"] for row in rows] == ["baby sleeping bag"]
    assert exclusions == []


def test_an_exact_negative_does_not_block_a_longer_converting_term():
    rows, _ = _select(_frame(
        _row(term="baby sleeping bag", clicks=25, keyword_text="kids bag"),
        _converting_row("baby sleeping bag 2.5 tog", keyword_text="kids bag"),
    ))

    assert [(row["keyword_text"], row["match_type"]) for row in rows] == [("baby sleeping bag", NEGATIVE_EXACT)]


# Anti-self: a keyword's own text is never negated in its own ad group (INV-10)

@pytest.mark.parametrize("keyword_type", ["BROAD", "PHRASE", "EXACT"])
def test_an_exact_negative_equal_to_a_keyword_of_its_ad_group_is_excluded(keyword_type):
    rows, exclusions = _select(_frame(
        _row(term="Sleeping  Bags", clicks=25, keyword_text="sleeping bag", keyword_type=keyword_type,
             keyword_status="PAUSED"),
    ))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_OWN_KEYWORD]


def test_a_phrase_negative_inside_a_broad_keyword_of_its_ad_group_is_excluded():
    rows, exclusions = _select(_frame(_low_ctr_row("sleeping bag", keyword_text="kids sleeping bag")))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_OWN_KEYWORD]


def test_a_keyword_of_another_ad_group_does_not_protect_the_term():
    rows, _ = _select(_frame(
        _row(term="sleeping bag", clicks=25, keyword_text="kids bag"),
        _row(term="otra busqueda", ad_group_id="400000000000009", keyword_text="sleeping bag", clicks=2),
    ))

    assert [row["keyword_text"] for row in rows] == ["sleeping bag"]


# Origin guard across the ad group (INV-11.1)

@pytest.mark.parametrize("sibling_origin, reason", [
    ("EXACT", EXCLUDED_EXACT_ORIGIN),
    ("PRODUCT_TARGETING", EXCLUDED_PRODUCT_TARGETING_ORIGIN),
])
def test_a_term_also_reached_through_exact_or_product_targeting_in_its_ad_group_is_excluded(sibling_origin, reason):
    rows, exclusions = _select(_frame(
        _row(term="sleeping bags", clicks=25, keyword_text="bag"),
        _row(term="Sleeping Bags", keyword_id="500000000000002", keyword_type=sibling_origin, origin=sibling_origin,
             match_type="EXACT", keyword_text="sleeping bag", clicks=10),
    ))

    assert rows == []
    assert _reasons(exclusions) == [reason]


def test_an_exact_origin_row_in_another_ad_group_does_not_block_the_term():
    rows, _ = _select(_frame(
        _row(term="sleeping bags", clicks=25, keyword_text="bag"),
        _row(term="sleeping bags", ad_group_id="400000000000009", keyword_type="EXACT", origin="EXACT",
             match_type="EXACT", keyword_text="sleeping bag", clicks=10),
    ))

    assert [row["keyword_text"] for row in rows] == ["sleeping bags"]


# RANKING and unnamed portfolios are protected term by term (INV-11.3)

def test_an_unnamed_portfolio_is_excluded_as_possibly_ranking_until_released():
    frame = _frame(_row(clicks=25, portfolio="Portfolio 987", portfolio_name_missing=True))

    rows, exclusions = _select(frame)
    released_rows, released_exclusions = _select(frame, released_ranking=frozenset({
        negative_key(exclusions[0].candidate)}))

    assert rows == []
    assert "Portfolio 987" in exclusions[0].reason and "RANKING" in exclusions[0].reason
    assert exclusions[0].releasable is True
    assert len(released_rows) == 1 and released_exclusions == []


def test_releasing_one_ranking_term_keeps_the_others_protected():
    frame = _frame(
        _row(term="termo rosa", clicks=25, portfolio="RANKING Core"),
        _row(term="termo azul", clicks=30, portfolio="RANKING Core"),
    )
    candidates = _candidates(frame)
    pink = next(candidate for candidate in candidates if candidate.search_term == "termo rosa")

    rows, exclusions = select_for_bulk(candidates, frame, released_ranking=frozenset({negative_key(pink)}))

    assert [row["keyword_text"] for row in rows] == ["termo rosa"]
    assert [exclusion.candidate.search_term for exclusion in exclusions] == ["termo azul"]
    assert exclusions[0].releasable is True


def test_a_release_key_does_not_lift_any_other_guard():
    frame = _frame(_row(term="termo", clicks=25, portfolio="RANKING Core", status="PAUSED"))
    candidate = _only(frame)

    rows, exclusions = select_for_bulk([candidate], frame, released_ranking=frozenset({negative_key(candidate)}))

    assert rows == []
    assert "no está activa" in exclusions[0].reason
    assert exclusions[0].releasable is False


def test_negative_key_normalizes_the_term():
    candidate = _only(_frame(_row(term="  Termo   ROSA ", clicks=25)))

    assert negative_key(candidate) == ("300000000000001", "400000000000001", "termo rosa", NEGATIVE_EXACT)


# Keyword Text that Amazon rejects never reaches the bulk

@pytest.mark.parametrize("fields", [
    {"term": "warm sleeping bag for toddler", "impressions": 5000, "clicks": 2, "spend": 1.0},
    {"term": "what is the best swaddle for a newborn that sleeps hot", "clicks": 25},
    {"term": "x" * 81, "clicks": 25},
    {"term": "100% cotton t shirt", "clicks": 25},
    {"term": "1/2 tog sleeping bag", "clicks": 25},
    {"term": "is this safe for newborns?", "clicks": 25},
    {"term": '=hyperlink("http://example.invalid","x")', "clicks": 25},
])
def test_keyword_text_amazon_rejects_is_excluded_with_the_reason(fields):
    rows, exclusions = _select(_frame(_row(keyword_text="kids bag", **fields)))

    assert rows == []
    assert len(exclusions) == 1
    assert exclusions[0].reason.startswith("Amazon no acepta este texto como keyword negativa: ")


@pytest.mark.parametrize("fields", [
    {"term": "warm sleeping bag toddler", "impressions": 5000, "clicks": 2, "spend": 1.0},
    {"term": "what is the best swaddle for a newborn baby girl", "clicks": 25},
    {"term": "x" * 80, "clicks": 25},
    {"term": "mac & cheese bowl", "clicks": 25},
])
def test_keyword_text_at_amazon_limits_stays_eligible(fields):
    rows, _ = _select(_frame(_row(keyword_text="kids bag", **fields)))

    assert len(rows) == 1


# Book ASINs (ISBN-10) are not search queries

@pytest.mark.parametrize("term", ["0307474275", "030747427X", "030747427x"])
def test_isbn10_asin_terms_are_excluded(term):
    rows, exclusions = _select(_frame(_row(term=term, clicks=25)))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_NOT_A_QUERY]


@pytest.mark.parametrize("term", ["03074742751", "030747427", "03074742xx"])
def test_numbers_that_are_not_isbn10_stay_eligible(term):
    rows, _ = _select(_frame(_row(term=term, clicks=25)))

    assert len(rows) == 1


# Purchases in any attribution window protect the term (INV-2)

def test_a_term_with_fourteen_day_purchases_only_is_never_a_bulk_negative():
    rows, exclusions = _select(_frame(_row(clicks=25, orders=0, any_window_purchases=3)))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_CONVERTS]


def test_a_sibling_row_with_fourteen_day_purchases_protects_the_term():
    rows, exclusions = _select(_frame(
        _row(clicks=25),
        _row(term="Jabon Neutro Bebe", keyword_id="500000000000009", clicks=2, orders=0, any_window_purchases=1),
    ))

    assert rows == []
    assert _reasons(exclusions) == [EXCLUDED_CONVERTS]


def test_provider_frame_keeps_unnamed_portfolio_and_fourteen_day_purchases_out_of_the_bulk():
    option = ProfileOption.from_row({"profile_id": "1111222233334444", "cliente": "Marca Demo", "country_code": "MX",
                                     "account_type": "seller", "status": "active"})
    csv_bytes = _api_csv([
        {"search_term": "jabon sin aroma"},
        {"search_term": "jabon en barra", "portfolio_id": "987", "portfolio_name": ""},
        {"search_term": "jabon de glicerina", "purchases_14d": "2", "sales_14d": "40"},
    ])
    source = ReportProvider(_FakeRest(csv_bytes)).search_terms(option, date(2026, 8, 31), date(2026, 9, 13))

    candidates = evaluate_candidates(source.frame, _detect_cols(source.frame), clicks_threshold=CLICKS_THRESHOLD,
                                     spend_threshold=SPEND_THRESHOLD)
    rows, exclusions = select_for_bulk(candidates, source.frame)
    reasons = {exclusion.candidate.search_term: exclusion.reason for exclusion in exclusions}

    assert [row["keyword_text"] for row in rows] == ["jabon sin aroma"]
    assert reasons["jabon de glicerina"] == EXCLUDED_CONVERTS
    assert "Portfolio 987" in reasons["jabon en barra"]

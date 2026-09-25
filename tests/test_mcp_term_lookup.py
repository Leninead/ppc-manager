"""targets: whether an account has each of a list of keywords or ASIN targets, one row per term."""
from __future__ import annotations

import pytest

from services.mcp_server.tools.term_lookup import MAX_LOOKUP_TERMS, expression_value, lookup_terms

ROWS = [
    {"campaign": "Exact", "campaign_id": "1", "target": "vitamin a cream", "match_type": "EXACT", "kind": "Keyword",
     "state": "ENABLED", "campaign_state": "ENABLED", "bid": 1.2, "spend": 10.0, "sales": 40.0, "orders": 2,
     "clicks": 8, "impressions": 100},
    {"campaign": "Phrase", "campaign_id": "2", "target": "vitamin a cream", "match_type": "PHRASE", "kind": "Keyword",
     "state": "ENABLED", "campaign_state": "PAUSED", "bid": 0.9, "spend": 5.0, "sales": 0.0, "orders": 0,
     "clicks": 4, "impressions": 60},
    {"campaign": "PAT", "campaign_id": "3", "target": 'asin="B0OWN00001"', "match_type": "", "kind": "Producto",
     "state": "PAUSED", "campaign_state": "ENABLED", "bid": 0.5},
]


def test_each_term_gets_one_row_found_or_not_with_where_it_runs_and_its_figures():
    """#86 asked twenty times in a row whether the account had each keyword."""
    rows = lookup_terms(ROWS, ["Vitamin A Cream", "night cream"], "exact")

    assert rows[0]["found"] is True and rows[0]["running"] is True
    assert rows[0]["match_types"] == ["EXACT", "PHRASE"]
    assert [place["campaign"] for place in rows[0]["campaigns"]] == ["Exact", "Phrase"]
    assert (rows[0]["spend"], rows[0]["orders"], rows[0]["acos"]) == (15.0, 2, 37.5)
    assert rows[1] == {"term": "night cream", "found": False}


def test_an_asin_finds_the_product_target_that_aims_exactly_at_it():
    [row] = lookup_terms(ROWS, ["b0own00001"], "exact")

    assert row["found"] is True and row["running"] is False and "spend" not in row


def test_contains_finds_the_term_inside_a_longer_one():
    assert lookup_terms(ROWS, ["vitamin"], "contains")[0]["found"] is True
    assert lookup_terms(ROWS, ["vitamin"], "exact")[0]["found"] is False


def test_a_list_too_long_or_empty_is_refused():
    with pytest.raises(ValueError, match=str(MAX_LOOKUP_TERMS)):
        lookup_terms(ROWS, [f"term {n}" for n in range(MAX_LOOKUP_TERMS + 1)], "exact")
    with pytest.raises(ValueError, match="al menos un término"):
        lookup_terms(ROWS, ["  "], "exact")
    with pytest.raises(ValueError, match="exact o contains"):
        lookup_terms(ROWS, ["x"], "fuzzy")


def test_only_a_single_predicate_expression_reads_as_one_value():
    assert expression_value('asin="b0x"') == "b0x"
    assert expression_value('category="123" brand="4"') == 'category="123" brand="4"'
    assert expression_value("vitamin a cream") == "vitamin a cream"

"""filters and sort_order: one way to ask for rows by their figures, the same in every tool that lists them."""
from __future__ import annotations

import pytest

from services.mcp_server.tools.metric_filters import (
    FILTER_METRICS,
    FILTERS_NOTE,
    RowFilter,
    _filters_schema,
    sort_rows,
    with_sort_figure,
)

ROWS = [
    {"group": "a", "spend": 30.0, "sales": 120.0, "orders": 4, "clicks": 40, "impressions": 800, "acos": 25.0},
    {"group": "b", "spend": 10.0, "sales": 0.0, "orders": 0, "clicks": 12, "impressions": 300, "acos": None},
    {"group": "c", "spend": 5.0, "sales": 50.0, "orders": 2, "clicks": 5, "impressions": 100, "acos": 10.0},
]


def _kept(filters: dict) -> list[str]:
    row_filter = RowFilter.from_request(filters)
    return [row["group"] for row in ROWS if row_filter.keeps(row)]


def test_every_bound_must_hold_unless_any_one_is_asked_for():
    """Before, every filter combined with AND and an «or» took one call per condition."""
    assert _kept({"min_orders": 2, "max_acos": 20}) == ["c"]
    assert _kept({"min_orders": 3, "max_acos": 12, "combine": "any"}) == ["a", "c"]


def test_a_zero_bound_is_a_bound_and_not_a_missing_filter():
    assert _kept({"max_orders": 0}) == ["b"]


def test_a_row_without_the_figure_never_meets_a_bound_on_it():
    """An ACoS that does not exist is neither under nor over 30%."""
    assert _kept({"max_acos": 30}) == ["a", "c"]
    assert _kept({"min_acos": 0}) == ["a", "c"]


def test_without_sales_keeps_the_rows_that_spent_and_sold_nothing():
    assert _kept({"without_sales": True}) == ["b"]


def test_an_unknown_bound_is_refused_with_the_ones_that_exist():
    with pytest.raises(ValueError, match="min_order"):
        RowFilter.from_request({"min_order": 2})
    with pytest.raises(ValueError, match="combine"):
        RowFilter.from_request({"combine": "some"})


def test_a_bound_on_a_figure_the_rows_do_not_carry_is_refused():
    with pytest.raises(ValueError, match="bid_gap no se puede usar acá"):
        RowFilter.from_request({"min_bid_gap": 0.1}, metrics=("spend", "orders"))


def test_the_filter_is_described_as_asked_and_combine_only_when_it_is_any():
    assert RowFilter.from_request({"min_orders": 2, "max_acos": 30}).described() == {
        "filters": {"min_orders": 2, "max_acos": 30}, "filters_note": FILTERS_NOTE}
    assert RowFilter.from_request({"min_orders": 2, "combine": "any"}).described()["filters"] == {
        "min_orders": 2, "combine": "any"}
    assert RowFilter.from_request(None).described() == {}


def test_rows_sort_either_way_and_the_ones_without_the_figure_go_last_in_both():
    assert [row["group"] for row in sort_rows(ROWS, "acos", "desc")] == ["a", "c", "b"]
    assert [row["group"] for row in sort_rows(ROWS, "acos", "asc")] == ["c", "a", "b"]
    with pytest.raises(ValueError, match="sort_order"):
        sort_rows(ROWS, "acos", "up")


def test_ctr_and_aov_travel_in_a_row_only_when_the_list_is_ordered_by_them():
    rows = with_sort_figure([dict(row) for row in ROWS], "ctr")

    assert [row["ctr"] for row in rows] == [5.0, 4.0, 5.0]
    assert "aov" not in rows[0]
    assert with_sort_figure([dict(ROWS[1])], "aov")[0]["aov"] is None


def test_the_published_schema_names_every_bound_with_its_type():
    """A property without its own type reaches the model untyped, so filters is a plain typed object."""
    schema = _filters_schema()

    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert {f"min_{metric}" for metric in FILTER_METRICS} <= set(schema["properties"])
    assert schema["properties"]["min_orders"] == {"type": "integer"}
    assert schema["properties"]["max_acos"] == {"type": "number"}
    assert schema["properties"]["without_sales"] == {"type": "boolean"}
    assert schema["properties"]["combine"] == {"type": "string", "enum": ["all", "any"]}

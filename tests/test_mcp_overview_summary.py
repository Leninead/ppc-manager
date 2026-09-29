"""The overview's summary: every account counted and ranked, so «how are the ads doing?» needs no paging."""
from services.mcp_server.tools.overview_summary import overview_summary


def _account(name: str, currency: str, spend, sales, *, previous_spend=None, previous_sales=None,
             delta_spend_pct=None, delta_sales_pct=None, delta_orders_pct=None, delta_acos_pp=None) -> dict:
    return {"account": name, "profile_id": name.lower(), "currency": currency, "spend": spend, "sales": sales,
            "orders": 1 if sales else 0, "clicks": 10, "spend_exceeds_sales": bool(spend and spend > (sales or 0)),
            "without_sales": bool(spend and not sales), "previous_spend": previous_spend,
            "previous_sales": previous_sales, "delta_spend_pct": delta_spend_pct,
            "delta_sales_pct": delta_sales_pct, "delta_orders_pct": delta_orders_pct,
            "delta_acos_pp": delta_acos_pp}


ROWS = [
    _account("Alfa", "USD", 100.0, 400.0, previous_spend=80.0, previous_sales=500.0, delta_spend_pct=25.0,
             delta_sales_pct=-20.0, delta_orders_pct=-10.0, delta_acos_pp=9.0),
    _account("Beta", "USD", 50.0, 0.0, previous_spend=50.0, previous_sales=100.0, delta_spend_pct=0.0,
             delta_sales_pct=-100.0, delta_orders_pct=-100.0, delta_acos_pp=None),
    _account("Gama", "MXN", 1000.0, 5000.0, previous_spend=2000.0, previous_sales=4000.0, delta_spend_pct=-50.0,
             delta_sales_pct=25.0, delta_orders_pct=0.0, delta_acos_pp=-30.0),
    _account("Quieta", "USD", 0.0, 0.0),
    {"account": "Sin datos", "profile_id": "x", "currency": "USD", "spend": None},
]


def test_the_summary_counts_every_account_not_only_the_page():
    """Asked how all the accounts were doing, the chat paged 52 accounts and counted the rises in its reasoning."""
    summary = overview_summary(ROWS, compared=True)

    assert (summary["accounts"], summary["with_spend"]) == (5, 3)
    assert summary["without_spend"] == ["Quieta"] and summary["without_figures"] == ["Sin datos"]
    assert (summary["spend_exceeds_sales"], summary["without_sales"]) == (1, 1)
    assert summary["changes"]["sales"] == {"up": 1, "down": 2, "flat": 0, "without_previous": 0}
    assert summary["changes"]["acos_points"] == {"up": 1, "down": 1, "flat": 0, "without_previous": 1}


def test_movers_rank_by_percentage_which_compares_across_currencies():
    movers = overview_summary(ROWS, compared=True)["movers"]

    assert [row["account"] for row in movers["sales_drop"]] == ["Beta", "Alfa"]
    assert [row["account"] for row in movers["sales_rise"]] == ["Gama"]
    assert movers["spend_drop"][0] == {"account": "Gama", "profile_id": "gama", "currency": "MXN",
                                       "delta_spend_pct": -50.0, "spend": 1000.0, "previous_spend": 2000.0}
    # The rows carry the ACoS now and its change in points, not the ACoS before: no empty field stands in for it.
    assert set(movers["acos_rise"][0]) == {"account", "profile_id", "currency", "delta_acos_pp", "acos"}


def test_amounts_add_up_only_within_one_currency():
    usd, mxn = overview_summary(ROWS, compared=True)["by_currency"]

    assert (usd["currency"], usd["accounts"], usd["spend"], usd["sales"], usd["acos"]) == ("USD", 2, 150.0, 400.0,
                                                                                          37.5)
    assert (usd["previous_sales"], usd["delta_sales_pct"]) == (600.0, -33.3)
    assert (mxn["currency"], mxn["delta_spend_pct"]) == ("MXN", -50.0)


def test_without_a_comparison_there_are_no_changes_to_count():
    summary = overview_summary(ROWS, compared=False)

    assert "changes" not in summary and "movers" not in summary
    assert "delta_spend_pct" not in summary["by_currency"][0]

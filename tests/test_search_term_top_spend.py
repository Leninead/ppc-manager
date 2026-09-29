"""The top campaigns by spend of the Por Campana tab (modules/pages/search_term_report._top_spend_rows)."""
import pandas as pd

from modules.pages.search_term_report import TOP_SPEND_LIMIT, _top_spend_rows


def _campaigns(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Campaign", "Spend", "Sales"])


def test_the_campaigns_that_spent_the_most_come_first_with_their_share_of_the_spend():
    rows = _top_spend_rows(_campaigns(("Low", 10.0, 50.0), ("High", 30.0, 60.0), ("Mid", 20.0, 0.0)), "USD")

    assert [row.name for row in rows] == ["High", "Mid", "Low"]
    assert [row.amount for row in rows] == ["$30.00", "$20.00", "$10.00"]
    assert [round(row.share, 1) for row in rows] == [50.0, 33.3, 16.7]


def test_acos_is_spend_over_sales_and_a_campaign_that_sold_nothing_says_so():
    rows = _top_spend_rows(_campaigns(("Seller", 30.0, 60.0), ("Bleeder", 20.0, 0.0)), "USD")

    assert [row.note for row in rows] == ["ACoS 50.0%", "Sin ventas"]


def test_only_the_top_five_are_listed_while_the_share_counts_every_campaign():
    campaigns = _campaigns(*[(f"Campaign {spend}", float(spend), 1.0) for spend in range(1, 8)])

    rows = _top_spend_rows(campaigns, "USD")

    assert TOP_SPEND_LIMIT == 5
    assert [row.name for row in rows] == ["Campaign 7", "Campaign 6", "Campaign 5", "Campaign 4", "Campaign 3"]
    assert round(rows[0].share, 2) == round(7 / 28 * 100, 2)


def test_a_campaign_that_spent_nothing_is_left_out_and_no_spend_at_all_lists_nothing():
    assert [row.name for row in _top_spend_rows(_campaigns(("Spent", 5.0, 0.0), ("Idle", 0.0, 0.0)), "USD")] == [
        "Spent"]
    assert _top_spend_rows(_campaigns(("Idle", 0.0, 0.0)), "USD") == []


def test_amounts_read_in_the_account_currency():
    assert _top_spend_rows(_campaigns(("Mexico", 12.5, 0.0)), "MXN")[0].amount == "MX$12.50"


def test_equal_spend_keeps_a_stable_order_by_name():
    rows = _top_spend_rows(_campaigns(("Beta", 10.0, 0.0), ("Alpha", 10.0, 0.0)), "USD")

    assert [row.name for row in rows] == ["Alpha", "Beta"]

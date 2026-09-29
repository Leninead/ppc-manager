"""The rules Account Pulse keeps out of the page: the kind of each day, the Buy Box alerts and the campaign list."""
from datetime import date

import pandas as pd

from core.account_pulse.buybox import buybox_alerts
from core.account_pulse.campaigns import campaign_age, campaign_rows
from core.account_pulse.day_types import day_type


def test_a_day_is_a_mexican_holiday_a_weekend_or_a_working_day():
    assert day_type(date(2026, 9, 16)) == ("Festivo", "Independencia")
    assert day_type(date(2026, 9, 19)) == ("Finde", None)
    assert day_type(date(2026, 9, 21)) == ("Laboral", None)


def test_a_holiday_on_a_weekend_is_still_the_holiday():
    assert day_type(date(2027, 12, 25)) == ("Festivo", "Navidad")


def test_the_buybox_alerts_are_the_asins_below_95_with_sessions_most_lost_sales_first():
    br_child = {
        "B0SMALL001": {"Title": "Small", "Sales": 100.0, "Sessions": 10, "BuyBox": 50.0},
        "B0BIG00001": {"Title": "Big", "Sales": 1000.0, "Sessions": 50, "BuyBox": 90.0},
        "B0HEALTHY1": {"Title": "Healthy", "Sales": 900.0, "Sessions": 40, "BuyBox": 99.0},
        "B0UNKNOWN1": {"Title": "No sessions", "Sales": 0.0, "Sessions": 0, "BuyBox": None},
    }

    alerts = buybox_alerts(br_child)

    # Big loses 1,000 x 10% = 100; Small loses 100 x 50% = 50.
    assert [(alert["asin"], alert["lost_sales"]) for alert in alerts] == [("B0BIG00001", 100.0), ("B0SMALL001", 50.0)]


def test_a_campaign_is_new_when_its_name_follows_the_capybaras_convention():
    assert campaign_age("Luna - B0TEST0001 - SP - KW - EXACT - Brand") == "NUEVA"
    assert campaign_age("Luna - SD - RET - Views") == "NUEVA"
    assert campaign_age("Campaña de verano 2026") == "NUEVA"
    assert campaign_age("Auto campaign from the old agency") == "HEREDADA"


def _totals(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["product", "campaign_id", "campaign", "spend", "sales", "orders", "clicks",
                                       "impressions"])


def test_the_campaigns_come_most_spend_first_with_ties_in_a_fixed_order():
    totals = _totals([("SP", "3", "Tie B", 10.0, 50.0, 1, 5, 100), ("SB", "9", "Top", 90.0, 300.0, 6, 40, 900),
                      ("SP", "1", "Tie A", 10.0, 20.0, 1, 5, 100)])

    rows = campaign_rows(totals)

    assert [row["Campaign"] for row in rows] == ["Top", "Tie A", "Tie B"]
    assert rows[0] == {"Campaign": "Top", "Product": "SB", "Age": "HEREDADA", "Impressions": 900, "Clicks": 40,
                       "Spend": 90.0, "Sales": 300.0, "ACoS": 30.0, "Orders": 6}


def test_a_campaign_that_sold_nothing_has_no_acos_instead_of_the_best_one():
    rows = campaign_rows(_totals([("SP", "1", "Bleeding", 25.0, 0.0, 0, 12, 400)]))

    assert rows[0]["ACoS"] is None

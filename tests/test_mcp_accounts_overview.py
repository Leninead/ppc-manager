"""accounts_overview: every synced account's totals in one call, so crossing accounts never takes thirty."""
from __future__ import annotations

from services.mcp_server.tools import amazon_ads


def _profile(profile_id, cliente, country, currency, data_through="2026-09-16", account_type="seller"):
    return {"profile_id": profile_id, "account_id": 7, "cliente": cliente, "account_name": cliente,
            "country_code": country, "currency_code": currency, "account_type": account_type, "timezone": "",
            "status": "active", "data_from": "2026-07-01", "data_through": data_through,
            "refreshed_on": "2026-09-17", "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": ""}


def _day(day, cost, sales, orders, clicks=20, impressions=500):
    return {"report_date": day, "impressions": impressions, "clicks": clicks, "cost": cost, "purchases_7d": orders,
            "sales_7d": sales, "purchases_14d": orders, "sales_14d": sales, "currency_code": "", "campaign_names": None}


class _FakeRest:
    def __init__(self, profiles, days_by_profile):
        self._profiles = profiles
        self._days = days_by_profile
        self.rpc_calls: list[dict] = []

    def select(self, table, params):
        return self._profiles

    def rpc(self, name, args, *, timeout_s=8):
        self.rpc_calls.append(args)
        return self._days.get(args["p_profile_id"], [])


def _overview(**kwargs):
    rest = _FakeRest(
        [_profile("1", "wamery", "US", "USD"), _profile("2", "wamery", "MX", "MXN"),
         _profile("3", "harrick", "US", "USD"), _profile("4", "nueva", "US", "USD", data_through=None)],
        {"1": [_day("2026-09-15", 30.0, 120.0, 4), _day("2026-09-16", 10.0, 0.0, 0)],
         "2": [_day("2026-09-16", 500.0, 1000.0, 5)]})
    return amazon_ads.accounts_overview(rest, **kwargs), rest


def test_every_synced_account_comes_back_with_its_totals_in_one_call():
    payload, rest = _overview(days=2)

    rows = {row["account"]: row for row in payload["rows"]}
    assert set(rows) == {"wamery · US", "wamery · MX", "harrick · US"}
    wamery = rows["wamery · US"]
    assert (wamery["spend"], wamery["sales"], wamery["orders"], wamery["acos"], wamery["currency"]) == (
        40.0, 120.0, 4, 33.3, "USD")
    assert payload["total"] == 3 and len(rest.rpc_calls) == 3


def test_an_account_that_did_not_spend_is_listed_with_zeros_not_left_out():
    """Leaving it out would read as "no such account"; a zero says it exists and was quiet."""
    rows = {row["account"]: row for row in _overview(days=2)[0]["rows"]}

    assert rows["harrick · US"]["spend"] == 0.0 and rows["harrick · US"]["acos"] is None


def test_each_account_keeps_its_currency_and_the_answer_warns_against_adding_them_up():
    payload, _ = _overview(days=2)

    assert {row["currency"] for row in payload["rows"]} == {"USD", "MXN"}
    assert "moneda" in payload["note"]


def test_each_account_says_which_window_it_covers():
    row = next(row for row in _overview(days=7)[0]["rows"] if row["account"] == "wamery · US")

    assert row["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}


def test_the_overview_says_it_is_sponsored_products():
    assert "Sponsored Products" in _overview()[0]["source"]

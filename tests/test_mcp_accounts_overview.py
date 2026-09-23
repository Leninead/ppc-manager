"""accounts_overview: every synced account's totals in one call, so crossing accounts never takes thirty."""
from __future__ import annotations

import pytest

from services.mcp_server.tools import amazon_ads


def _profile(profile_id, cliente, country, currency, data_through="2026-09-16", account_type="seller"):
    return {"profile_id": profile_id, "account_id": 7, "cliente": cliente, "account_name": cliente,
            "country_code": country, "currency_code": currency, "account_type": account_type, "timezone": "",
            "status": "active", "data_from": "2026-07-01", "data_through": data_through,
            "refreshed_on": "2026-09-17", "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": ""}


def _campaign_job(profile_id):
    """The campaign sync each account's window comes from."""
    return {"id": int(profile_id), "integration_slug": "amazon_ads", "job_kind": "sp_campaigns",
            "trigger": "scheduled_daily", "external_account_id": profile_id, "status": "completed",
            "window_start": "2026-07-14", "window_end": "2026-09-16", "local_day": "2026-09-17",
            "finished_at": "2026-09-17T11:05:00+00:00", "created_at": "2026-09-17T10:43:00+00:00"}


def _day(day, cost, sales, orders, clicks=20, impressions=500, ad_product="SP"):
    sp = ad_product == "SP"
    return {"report_date": day, "ad_product": ad_product, "impressions": impressions, "clicks": clicks, "cost": cost,
            "purchases_7d": orders if sp else 0, "sales_7d": sales if sp else 0, "purchases_14d": orders if sp else 0,
            "sales_14d": sales if sp else 0, "purchases": 0 if sp else orders, "sales": 0 if sp else sales,
            "purchases_clicks": 0 if sp else orders, "sales_clicks": 0 if sp else sales, "currency_code": "",
            "campaign_names": None}


def _term_day(day, cost, sales, orders, clicks=20, impressions=200):
    """SP summed from the search terms: only the terms with clicks, so fewer impressions."""
    return {"report_date": day, "impressions": impressions, "clicks": clicks, "cost": cost, "purchases_7d": orders,
            "sales_7d": sales, "purchases_14d": orders, "sales_14d": sales, "currency_code": "", "campaign_names": None}


class _FakeRest:
    def __init__(self, profiles, days_by_profile, synced=("1", "2", "3"), term_days_by_profile=None):
        self._profiles = profiles
        self._days = days_by_profile
        self._term_days = term_days_by_profile or {}
        self._synced = synced
        self.rpc_calls: list[dict] = []
        self.rpc_names: list[str] = []

    def select(self, table, params):
        if table == "integration_sync_jobs":
            profile_id = params["external_account_id"].removeprefix("eq.")
            return [_campaign_job(profile_id)] if profile_id in self._synced else []
        return self._profiles

    def rpc(self, name, args, *, timeout_s=8):
        assert name in ("campaign_daily_totals", "ads_daily_totals")
        self.rpc_calls.append(args)
        self.rpc_names.append(name)
        days = self._days if name == "campaign_daily_totals" else self._term_days
        return days.get(args["p_profile_id"], [])


def _overview(synced=("1", "2", "3"), **kwargs):
    rest = _FakeRest(
        [_profile("1", "wamery", "US", "USD"), _profile("2", "wamery", "MX", "MXN"),
         _profile("3", "harrick", "US", "USD"), _profile("4", "nueva", "US", "USD", data_through=None)],
        {"1": [_day("2026-09-15", 30.0, 120.0, 4), _day("2026-09-16", 10.0, 0.0, 0),
               _day("2026-09-16", 20.0, 80.0, 2, ad_product="SB")],
         "2": [_day("2026-09-16", 500.0, 1000.0, 5)]},
        synced=synced,
        term_days_by_profile={"1": [_term_day("2026-09-15", 30.0, 120.0, 4), _term_day("2026-09-16", 10.0, 0.0, 0)]})
    return amazon_ads.accounts_overview(rest, **kwargs), rest


def test_every_synced_account_comes_back_with_its_totals_in_one_call():
    payload, rest = _overview(days=2)

    rows = {row["account"]: row for row in payload["rows"]}
    assert set(rows) == {"wamery · US", "wamery · MX", "harrick · US"}
    wamery = rows["wamery · US"]
    # SB's day adds to SP's: the account's campaigns of every product.
    assert (wamery["spend"], wamery["sales"], wamery["orders"], wamery["acos"], wamery["currency"]) == (
        60.0, 200.0, 6, 30.0, "USD")
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


def test_every_account_is_read_over_the_same_exact_period_when_one_is_asked_for():
    """Comparing a month with the one before takes two calls, not subtracting totals."""
    payload, rest = _overview(date_from="2026-09-01", date_to="2026-09-15")

    assert {(call["p_from"], call["p_to"]) for call in rest.rpc_calls} == {("2026-09-01", "2026-09-15")}
    assert {row["window"]["from"] for row in payload["rows"]} == {"2026-09-01"}
    assert all("window_note" not in row for row in payload["rows"])


def test_a_period_past_the_synced_days_is_cut_and_says_so():
    row = next(row for row in _overview(date_from="2026-09-10", date_to="2026-09-20")[0]["rows"]
               if row["account"] == "wamery · US")

    assert row["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}
    assert "se recortó" in row["window_note"]


def test_an_account_without_data_in_the_period_comes_back_without_figures_not_as_zero():
    """A zero would say it did not spend; it simply had nothing synced then."""
    row = next(row for row in _overview(date_from="2026-06-01", date_to="2026-06-10")[0]["rows"]
               if row["account"] == "wamery · US")

    assert row["window"] is None and "spend" not in row
    assert "queda afuera" in row["window_note"]


@pytest.mark.parametrize("period", [{"date_from": "2026-09-01"}, {"date_from": "2026-09-15", "date_to": "2026-09-01"}])
def test_a_malformed_period_is_refused_before_any_account_is_read(period):
    rest = _FakeRest([_profile("1", "wamery", "US", "USD")], {})

    with pytest.raises(ValueError):
        amazon_ads.accounts_overview(rest, **period)
    assert rest.rpc_calls == []


def test_the_overview_says_it_covers_the_three_products():
    assert "Sponsored Products, Brands y Display" in _overview()[0]["source"]


def test_the_overview_tells_how_to_ask_for_sp_summed_from_the_search_terms():
    payload, _ = _overview()

    assert payload["data_source"] == "campaigns" and "source=search_terms" in payload["alternative"]


def test_sp_totals_from_the_search_terms_are_still_there_on_request():
    payload, rest = _overview(days=2, source="search_terms")

    assert set(rest.rpc_names) == {"ads_daily_totals"}
    rows = {row["account"]: row for row in payload["rows"]}
    wamery = rows["wamery · US"]
    # Only SP: SB's day is not in the search terms.
    assert (wamery["spend"], wamery["sales"], wamery["orders"], wamery["impressions"], wamery["acos"]) == (
        40.0, 120.0, 4, 400, 33.3)
    assert payload["data_source"] == "search_terms" and "source=campaigns" in payload["alternative"]


def test_the_search_term_overview_lists_the_accounts_with_search_terms_even_before_their_campaign_sync():
    payload, _ = _overview(synced=("1",), source="search_terms")

    assert {row["account"] for row in payload["rows"]} == {"wamery · US", "wamery · MX", "harrick · US"}
    assert "without_campaigns" not in payload


def test_accounts_whose_campaigns_are_not_synced_yet_are_named_instead_of_silently_missing():
    """Out of the rows they would read as accounts that do not exist; their SP is in the search terms."""
    payload, _ = _overview(synced=("1",))

    assert [row["account"] for row in payload["rows"]] == ["wamery · US"]
    assert payload["without_campaigns"] == ["harrick · US", "wamery · MX"]    # "nueva" has no data at all
    assert "source=search_terms" in payload["without_campaigns_note"]


def test_with_every_campaign_sync_done_no_account_is_named_as_missing():
    assert "without_campaigns" not in _overview()[0]


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError, match="campaigns, search_terms"):
        _overview(source="business_report")

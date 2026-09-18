"""daily_metrics: the series the chat needs to draw how an account or a campaign is doing."""
from __future__ import annotations

from datetime import date

from services.mcp_server.tools import amazon_ads

PROFILE = {
    "profile_id": "1111222233334444", "account_id": 7, "cliente": "Marca Demo", "account_name": "Demo LLC",
    "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "", "status": "active",
    "data_from": "2026-08-01", "data_through": "2026-09-16", "refreshed_on": "2026-09-17",
    "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": "",
}


class _FakeRest:
    def __init__(self, days=None, profile=None):
        self._days = list(days or [])
        self._profile = profile or PROFILE
        self.rpc_calls: list[dict] = []

    def select(self, table, params):
        return [self._profile]

    def rpc(self, name, args, *, timeout_s=8):
        self.rpc_calls.append(args)
        return self._days


def _day(day: str, **overrides) -> dict:
    row = {"report_date": day, "impressions": 1000, "clicks": 40, "cost": 30.0, "purchases_7d": 4,
           "sales_7d": 120.0, "purchases_14d": 6, "sales_14d": 200.0, "currency_code": "USD", "campaign_names": None}
    row.update(overrides)
    return row


def test_each_day_carries_the_metrics_the_chat_can_draw():
    rest = _FakeRest([_day("2026-09-16")])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)

    assert payload["rows"] == [{"date": "2026-09-16", "spend": 30.0, "sales": 120.0, "orders": 4, "clicks": 40,
                                "impressions": 1000, "acos": 25.0, "cvr": 10.0}]
    assert payload["currency"] == "USD" and payload["attribution_days"] == 7


def test_a_day_without_sales_has_no_acos_and_a_day_without_clicks_has_no_cvr():
    rest = _FakeRest([_day("2026-09-15", sales_7d=0, purchases_7d=0)])

    rows = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=2)["rows"]

    assert rows[0]["acos"] is None and rows[0]["cvr"] == 0.0
    assert rows[1] == {"date": "2026-09-16", "spend": 0.0, "sales": 0.0, "orders": 0, "clicks": 0,
                       "impressions": 0, "acos": None, "cvr": None}


def test_the_window_ends_on_the_last_synced_day_and_defaults_to_two_weeks():
    rest = _FakeRest()

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444")

    assert rest.rpc_calls[0]["p_from"] == "2026-09-03" and rest.rpc_calls[0]["p_to"] == "2026-09-16"
    assert payload["window"] == {"from": "2026-09-03", "to": "2026-09-16", "days": 14}
    assert len(payload["rows"]) == 14


def test_the_window_is_capped_and_clipped_to_what_the_account_has_synced():
    rest = _FakeRest()

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=365)

    assert payload["window"]["days"] == 47           # data_from 01/08 → 16/09, under the 60-day cap
    assert "window_note" in payload


def test_a_campaign_filter_names_the_campaigns_it_summed():
    rest = _FakeRest([_day("2026-09-16", campaign_names=["Demo - SP - KW - EXACT - cuchillo"])])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="cuchillo")

    assert rest.rpc_calls[0]["p_campaign"] == "cuchillo"
    assert payload["campaigns"] == ["Demo - SP - KW - EXACT - cuchillo"]


def test_a_campaign_that_matches_nothing_returns_no_days_instead_of_a_series_of_zeros():
    """A row of zeros would read as a campaign that stopped spending, not as a name that matched nothing."""
    payload = amazon_ads.daily_metrics(_FakeRest([]), profile_id="1111222233334444", days=7, campaign="inexistente")

    assert payload["rows"] == [] and payload["campaigns"] == []
    assert "inexistente" in payload["note"]


def test_a_short_fragment_that_matches_many_campaigns_lists_a_bounded_number_of_them():
    names = [f"Campaña {n:03d}" for n in range(amazon_ads.MAX_CAMPAIGNS_LISTED + 10)]
    rest = _FakeRest([_day("2026-09-16", campaign_names=names)])

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1, campaign="Campaña")

    assert len(payload["campaigns"]) == amazon_ads.MAX_CAMPAIGNS_LISTED
    assert payload["campaigns_total"] == len(names)


def test_the_series_says_it_is_sponsored_products_from_the_search_term_report():
    """The model must not present it as the account's whole ad spend: Brands and Display are not in it."""
    payload = amazon_ads.daily_metrics(_FakeRest(), profile_id="1111222233334444", days=1)

    assert "Sponsored Products" in payload["source"]


def test_a_vendor_account_reads_fourteen_day_attribution():
    rest = _FakeRest([_day("2026-09-16")], profile={**PROFILE, "account_type": "vendor"})

    payload = amazon_ads.daily_metrics(rest, profile_id="1111222233334444", days=1)

    assert payload["rows"][0]["orders"] == 6 and payload["attribution_days"] == 14


def test_the_window_helper_is_shared_with_top_search_terms():
    profile = amazon_ads.ReportProvider(_FakeRest()).profiles()[0]

    assert amazon_ads.window_for(profile, 7) == (date(2026, 9, 10), date(2026, 9, 16))
    assert amazon_ads.window_for(profile, 0) == (date(2026, 9, 16), date(2026, 9, 16))

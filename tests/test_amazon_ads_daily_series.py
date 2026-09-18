"""The daily series of one synced profile: what the chat draws when asked how an account or a campaign is doing."""
from __future__ import annotations

import pathlib
from datetime import date

import pytest
import requests

from core.amazon_ads.report_provider import (
    DAILY_TOTALS_RPC,
    READ_TIMEOUT_SECONDS,
    ProfileOption,
    ReportProvider,
    ReportReadError,
)

START, END = date(2026, 9, 10), date(2026, 9, 13)


class _FakeRest:
    def __init__(self, rows=None, fail_with=None):
        self._rows = list(rows or [])
        self._fail_with = fail_with
        self.rpc_calls: list[tuple[str, dict, int]] = []

    def rpc(self, name, args, *, timeout_s=8):
        self.rpc_calls.append((name, args, timeout_s))
        if self._fail_with:
            raise self._fail_with
        return self._rows


def _option(account_type: str = "seller") -> ProfileOption:
    return ProfileOption.from_row({
        "profile_id": "1111222233334444", "account_id": 7, "cliente": "Marca Demo", "account_name": "Demo LLC",
        "country_code": "US", "currency_code": "USD", "account_type": account_type, "timezone": "",
        "status": "active", "data_from": "2026-07-11", "data_through": "2026-09-13", "refreshed_on": "2026-09-14",
        "last_success_at": "2026-09-14T11:05:00+00:00", "last_error": "",
    })


def _day(day: str, **overrides) -> dict:
    row = {"report_date": day, "impressions": 1000, "clicks": 40, "cost": 30.5, "purchases_7d": 3,
           "sales_7d": 120.0, "purchases_14d": 5, "sales_14d": 200.0, "currency_code": "USD",
           "campaign_names": None}
    row.update(overrides)
    return row


def test_every_day_of_the_window_is_in_the_series_even_the_ones_nothing_ran():
    rest = _FakeRest([_day("2026-09-10"), _day("2026-09-12", cost=10.0)])

    series = ReportProvider(rest).daily_totals(_option(), START, END)

    assert [day.day for day in series.days] == [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 12),
                                                date(2026, 9, 13)]
    assert [day.spend for day in series.days] == [30.5, 0.0, 10.0, 0.0]
    assert series.days[1].clicks == 0 and series.days[1].orders == 0


def test_a_seller_account_reads_seven_day_attribution_like_its_search_term_report():
    series = ReportProvider(_FakeRest([_day("2026-09-10")])).daily_totals(_option("seller"), START, START)

    assert (series.days[0].orders, series.days[0].sales) == (3, 120.0)
    assert series.attribution_days == 7


def test_a_vendor_account_reads_fourteen_day_attribution():
    series = ReportProvider(_FakeRest([_day("2026-09-10")])).daily_totals(_option("vendor"), START, START)

    assert (series.days[0].orders, series.days[0].sales) == (5, 200.0)
    assert series.attribution_days == 14


def test_the_database_sums_by_day_and_the_request_says_which_profile_window_and_campaign():
    rest = _FakeRest([])

    ReportProvider(rest).daily_totals(_option(), START, END, campaign="  SerratedSharpener ")

    name, args, timeout_s = rest.rpc_calls[0]
    assert name == DAILY_TOTALS_RPC and timeout_s == READ_TIMEOUT_SECONDS
    assert args == {"p_profile_id": "1111222233334444", "p_from": "2026-09-10", "p_to": "2026-09-13",
                    "p_campaign": "SerratedSharpener"}


def test_without_a_campaign_the_whole_account_is_summed():
    rest = _FakeRest([])

    series = ReportProvider(rest).daily_totals(_option(), START, END, campaign="   ")

    assert rest.rpc_calls[0][1]["p_campaign"] is None
    assert series.campaigns == ()


def test_a_campaign_filter_says_which_campaigns_it_summed():
    rest = _FakeRest([_day("2026-09-10", campaign_names=["B - PHRASE", "A - EXACT"]),
                      _day("2026-09-11", campaign_names=["A - EXACT"])])

    series = ReportProvider(rest).daily_totals(_option(), START, END, campaign="A")

    assert series.campaigns == ("A - EXACT", "B - PHRASE")


def test_the_currency_comes_from_the_profile_and_falls_back_to_the_rows():
    series = ReportProvider(_FakeRest([_day("2026-09-10")])).daily_totals(_option(), START, START)

    assert series.currency_code == "USD"


def test_an_inverted_window_is_a_caller_error():
    with pytest.raises(ValueError, match="ends before it starts"):
        ReportProvider(_FakeRest()).daily_totals(_option(), END, START)


def test_a_failed_read_explains_itself_instead_of_leaking_the_http_error():
    rest = _FakeRest(fail_with=requests.ConnectionError("refused"))

    with pytest.raises(ReportReadError, match="serie diaria"):
        ReportProvider(rest).daily_totals(_option(), START, END)


def test_a_row_the_database_should_never_send_is_a_read_error_not_a_crash():
    rest = _FakeRest([{"report_date": "no es una fecha"}])

    with pytest.raises(ReportReadError):
        ReportProvider(rest).daily_totals(_option(), START, END)


def test_the_web_role_can_call_the_daily_totals_function():
    """The MCP reads with the web_user JWT: a function it cannot execute answers 404 in production only."""
    migrations = "".join(path.read_text(encoding="utf-8")
                         for path in sorted(pathlib.Path("deploy/db/migrations").glob("*.sql")))

    assert f"function {DAILY_TOTALS_RPC}(" in migrations
    assert f"grant execute on function {DAILY_TOTALS_RPC}(text, date, date, text) to web_user" in migrations

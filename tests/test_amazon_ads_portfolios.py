"""Portfolios: paginated listing over the v3 API and upsert-only persistence. Fake session and fake rest."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.amazon_ads.api_client import AdsAccessDenied, AdsApiClient, AdsApiError
from core.amazon_ads.portfolios import (
    PORTFOLIO_CONTENT_TYPE,
    PORTFOLIOS_TABLE,
    fetch_portfolios,
    save_portfolios,
)


class _FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self.headers = {}
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class _FakeSession:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": json})
        return self._outcomes.pop(0)


class _FakeRest:
    def __init__(self):
        self.upserts = []

    def upsert(self, table, row, on_conflict=None):
        self.upserts.append((table, row, on_conflict))

    def update(self, *args, **kwargs):
        raise AssertionError("portfolios are never updated in place")

    def delete(self, *args, **kwargs):
        raise AssertionError("portfolios are never deleted")


def _api(outcomes):
    session = _FakeSession(outcomes)
    client = AdsApiClient(region="EU", client_id="client-abc", token_source=lambda force: "token",
                          session=session, sleep=lambda seconds: None)
    return client, session


def _portfolio(portfolio_id, name="Demo portfolio", state="ENABLED"):
    return {"portfolioId": portfolio_id, "name": name, "state": state, "inBudget": True}


def test_fetch_follows_next_token_until_the_last_page():
    api, session = _api([
        _FakeResponse(200, {"portfolios": [_portfolio("101", "Brand"), _portfolio("102", "Generic")],
                            "nextToken": "page-2"}),
        _FakeResponse(200, {"portfolios": [_portfolio(103, "Ranking", "ARCHIVED")]}),
    ])

    portfolios = fetch_portfolios(api, "555")

    assert portfolios == [
        {"portfolio_id": "101", "name": "Brand", "state": "ENABLED"},
        {"portfolio_id": "102", "name": "Generic", "state": "ENABLED"},
        {"portfolio_id": "103", "name": "Ranking", "state": "ARCHIVED"},
    ]
    assert [call["json"] for call in session.calls] == [{}, {"nextToken": "page-2"}]
    for call in session.calls:
        assert call["method"] == "POST"
        assert call["url"] == "https://advertising-api-eu.amazon.com/portfolios/list"
        assert call["headers"]["Content-Type"] == PORTFOLIO_CONTENT_TYPE
        assert call["headers"]["Amazon-Advertising-API-Scope"] == "555"


def test_fetch_with_no_portfolios_returns_empty_list():
    api, _ = _api([_FakeResponse(200, {"portfolios": [], "totalResults": 0})])

    assert fetch_portfolios(api, "555") == []


def test_fetch_skips_entries_without_an_id():
    api, _ = _api([_FakeResponse(200, {"portfolios": [{"name": "no id"}, _portfolio("9")]})])

    assert [portfolio["portfolio_id"] for portfolio in fetch_portfolios(api, "555")] == ["9"]


def test_fetch_stops_when_amazon_repeats_a_page_token():
    api, session = _api([
        _FakeResponse(200, {"portfolios": [_portfolio("1")], "nextToken": "same"}),
        _FakeResponse(200, {"portfolios": [_portfolio("2")], "nextToken": "same"}),
    ])

    assert len(fetch_portfolios(api, "555")) == 2
    assert len(session.calls) == 2


@pytest.mark.parametrize("status", [401, 403])
def test_view_only_profile_access_denied_propagates(status):
    api, _ = _api([_FakeResponse(status, {"code": "UNAUTHORIZED"})] * 2)

    with pytest.raises(AdsAccessDenied):
        fetch_portfolios(api, "555")


def test_unreadable_page_is_an_api_error():
    api, _ = _api([_FakeResponse(200, ["not", "an", "object"])])

    with pytest.raises(AdsApiError):
        fetch_portfolios(api, "555")


def test_save_upserts_rows_on_profile_and_portfolio_id():
    rest = _FakeRest()
    seen_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    saved = save_portfolios(rest, "555", [
        {"portfolio_id": "101", "name": "Brand", "state": "ENABLED"},
        {"portfolio_id": "102", "name": "Generic", "state": "PAUSED"},
    ], seen_at)

    assert saved == 2
    table, rows, on_conflict = rest.upserts[0]
    assert table == PORTFOLIOS_TABLE
    assert on_conflict == "profile_id,portfolio_id"
    assert rows == [
        {"profile_id": "555", "portfolio_id": "101", "name": "Brand", "state": "ENABLED",
         "seen_at": "2026-09-14T12:00:00+00:00"},
        {"profile_id": "555", "portfolio_id": "102", "name": "Generic", "state": "PAUSED",
         "seen_at": "2026-09-14T12:00:00+00:00"},
    ]


def test_save_collapses_duplicate_ids_in_one_batch():
    rest = _FakeRest()

    saved = save_portfolios(rest, "555", [
        {"portfolio_id": "101", "name": "Old name", "state": "ENABLED"},
        {"portfolio_id": "101", "name": "New name", "state": "ENABLED"},
    ], datetime(2026, 9, 14, tzinfo=timezone.utc))

    assert saved == 1
    assert [row["name"] for row in rest.upserts[0][1]] == ["New name"]


def test_save_nothing_writes_nothing():
    rest = _FakeRest()

    assert save_portfolios(rest, "555", [], datetime(2026, 9, 14, tzinfo=timezone.utc)) == 0
    assert rest.upserts == []

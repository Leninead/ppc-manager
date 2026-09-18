"""AdsApiClient: headers, retries with backoff, throttling, token refresh on 401 and access errors. No network."""
from __future__ import annotations

import json

import pytest
import requests

from core.amazon_ads.api_client import (
    CLIENT_ID_HEADER,
    SCOPE_HEADER,
    AdsAccessDenied,
    AdsApiClient,
    AdsApiError,
    AdsThrottled,
)


class _FakeResponse:
    def __init__(self, status_code: int, body=None, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if body is not None else {}
        self.text = body if isinstance(body, str) else json.dumps(self._body)

    def json(self):
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body


class _FakeSession:
    """Replays scripted outcomes in order; an Exception instance is raised instead of returned."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": json})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _TokenSource:
    def __init__(self):
        self.calls = []

    def __call__(self, force_refresh: bool) -> str:
        self.calls.append(force_refresh)
        return "fresh-token" if force_refresh else "cached-token"


def _client(session, tokens=None, **kwargs):
    sleeps = []
    client = AdsApiClient(
        region="NA",
        client_id="client-abc",
        token_source=tokens or _TokenSource(),
        session=session,
        sleep=sleeps.append,
        **kwargs,
    )
    return client, sleeps


def test_sends_client_id_bearer_scope_and_content_type_to_the_regional_host():
    session = _FakeSession([_FakeResponse(200, {"ok": True})])
    client, _ = _client(session)

    client.request("POST", "/portfolios/list", profile_id="123", json_body={}, content_type="application/x-test")

    call = session.calls[0]
    assert call["url"] == "https://advertising-api.amazon.com/portfolios/list"
    assert call["headers"][CLIENT_ID_HEADER] == "client-abc"
    assert call["headers"]["Authorization"] == "Bearer cached-token"
    assert call["headers"][SCOPE_HEADER] == "123"
    assert call["headers"]["Content-Type"] == "application/x-test"
    assert call["json"] == {}


def test_omits_scope_header_without_profile():
    session = _FakeSession([_FakeResponse(200)])
    client, _ = _client(session)

    client.request("GET", "/v2/profiles")

    assert SCOPE_HEADER not in session.calls[0]["headers"]
    assert "Amazon-Ads-AccountId" not in session.calls[0]["headers"]


def test_sends_accept_when_the_endpoint_needs_it():
    session = _FakeSession([_FakeResponse(200, {"campaigns": []})])
    client, _ = _client(session)

    client.request("POST", "/sp/campaigns/list", profile_id="123", json_body={},
                   content_type="application/vnd.spCampaign.v3+json",
                   accept="application/vnd.spCampaign.v3+json")

    assert session.calls[0]["headers"]["Accept"] == "application/vnd.spCampaign.v3+json"


def test_omits_accept_when_it_was_not_asked_for():
    session = _FakeSession([_FakeResponse(200)])
    client, _ = _client(session)

    client.request("POST", "/portfolios/list", profile_id="123", json_body={},
                   content_type="application/vnd.spPortfolio.v3+json")

    assert "Accept" not in session.calls[0]["headers"]


def test_unknown_region_is_rejected():
    with pytest.raises(ValueError):
        AdsApiClient(region="XX", client_id="c", token_source=lambda force: "t")


def test_client_id_source_is_read_for_every_request_after_the_token():
    events = []
    client_ids = iter(["client-before-swap", "client-after-swap"])

    def token_source(force_refresh: bool) -> str:
        events.append("token")
        return "token"

    def client_id_source() -> str:
        events.append("client id")
        return next(client_ids)

    session = _FakeSession([_FakeResponse(200), _FakeResponse(200)])
    client = AdsApiClient(region="NA", client_id_source=client_id_source, token_source=token_source, session=session)

    client.request("GET", "/x")
    client.request("GET", "/x")

    assert [call["headers"][CLIENT_ID_HEADER] for call in session.calls] == ["client-before-swap", "client-after-swap"]
    assert events == ["token", "client id", "token", "client id"]


def test_client_without_a_client_id_or_a_source_is_rejected():
    with pytest.raises(ValueError, match="client_id"):
        AdsApiClient(region="NA", token_source=lambda force: "t")


def test_server_errors_retry_with_exponential_backoff_then_succeed():
    session = _FakeSession([_FakeResponse(500), _FakeResponse(502), _FakeResponse(503), _FakeResponse(200)])
    client, sleeps = _client(session)

    response = client.request("GET", "/reporting/reports/r1", profile_id="1")

    assert response.status_code == 200
    assert sleeps == [1.0, 2.0, 4.0]
    assert len(session.calls) == 4


def test_server_errors_raise_after_max_retries():
    session = _FakeSession([_FakeResponse(500, "boom")] * 4)
    client, sleeps = _client(session)

    with pytest.raises(AdsApiError) as raised:
        client.request("GET", "/reporting/reports/r1", profile_id="1")

    assert raised.value.status == 500
    assert not isinstance(raised.value, (AdsThrottled, AdsAccessDenied))
    assert len(session.calls) == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_network_errors_retry_then_raise_without_status():
    session = _FakeSession([requests.ConnectionError("down")] * 3)
    client, sleeps = _client(session, max_retries=2)

    with pytest.raises(AdsApiError) as raised:
        client.request("GET", "/reporting/reports/r1")

    assert raised.value.status is None
    assert sleeps == [1.0, 2.0]


def test_network_error_recovers_on_retry():
    session = _FakeSession([requests.Timeout("slow"), _FakeResponse(200)])
    client, sleeps = _client(session)

    assert client.request("GET", "/x").status_code == 200
    assert sleeps == [1.0]


def test_throttle_honors_retry_after_header():
    session = _FakeSession([_FakeResponse(429, headers={"Retry-After": "7"}), _FakeResponse(200)])
    client, sleeps = _client(session)

    client.request("POST", "/reporting/reports", profile_id="1", json_body={})

    assert sleeps == [7.0]


def test_throttle_caps_retry_after_at_thirty_seconds():
    session = _FakeSession([_FakeResponse(429, headers={"Retry-After": "900"}), _FakeResponse(200)])
    client, sleeps = _client(session)

    client.request("GET", "/x")

    assert sleeps == [30.0]


def test_throttle_without_retry_after_uses_backoff():
    session = _FakeSession([_FakeResponse(429), _FakeResponse(429), _FakeResponse(200)])
    client, sleeps = _client(session)

    client.request("GET", "/x")

    assert sleeps == [1.0, 2.0]


def test_persistent_throttle_raises_ads_throttled_with_retry_after():
    session = _FakeSession([_FakeResponse(429, headers={"Retry-After": "12"})] * 4)
    client, sleeps = _client(session)

    with pytest.raises(AdsThrottled) as raised:
        client.request("GET", "/x")

    assert raised.value.status == 429
    assert raised.value.retry_after_s == 12.0
    assert len(session.calls) == 4
    assert sleeps == [12.0, 12.0, 12.0]


def test_unauthorized_forces_one_token_refresh_and_retries():
    tokens = _TokenSource()
    session = _FakeSession([_FakeResponse(401), _FakeResponse(200)])
    client, sleeps = _client(session, tokens=tokens)

    response = client.request("GET", "/reporting/reports/r1", profile_id="1")

    assert response.status_code == 200
    assert tokens.calls == [False, True]
    assert session.calls[1]["headers"]["Authorization"] == "Bearer fresh-token"
    assert sleeps == []


def test_unauthorized_after_refresh_is_access_denied():
    tokens = _TokenSource()
    session = _FakeSession([_FakeResponse(401), _FakeResponse(401)])
    client, _ = _client(session, tokens=tokens)

    with pytest.raises(AdsAccessDenied) as raised:
        client.request("GET", "/x", profile_id="1")

    assert raised.value.status == 401
    assert tokens.calls == [False, True]


def test_forbidden_after_refresh_is_access_denied():
    session = _FakeSession([_FakeResponse(401), _FakeResponse(403)])
    client, _ = _client(session)

    with pytest.raises(AdsAccessDenied) as raised:
        client.request("GET", "/x", profile_id="1")

    assert raised.value.status == 403


def test_forbidden_is_access_denied_without_refresh():
    tokens = _TokenSource()
    session = _FakeSession([_FakeResponse(403, {"code": "UNAUTHORIZED"})])
    client, _ = _client(session, tokens=tokens)

    with pytest.raises(AdsAccessDenied):
        client.request("POST", "/portfolios/list", profile_id="1", json_body={})

    assert tokens.calls == [False]
    assert len(session.calls) == 1


def test_unexpected_client_error_raises_with_status_and_body():
    session = _FakeSession([_FakeResponse(400, {"code": "400", "detail": "bad column"})])
    client, sleeps = _client(session)

    with pytest.raises(AdsApiError) as raised:
        client.request("POST", "/reporting/reports", profile_id="1", json_body={})

    assert raised.value.status == 400
    assert "bad column" in raised.value.body
    assert sleeps == []


def test_status_listed_as_expected_is_returned():
    session = _FakeSession([_FakeResponse(425, {"code": "425"})])
    client, _ = _client(session)

    response = client.request("POST", "/reporting/reports", json_body={}, expected=(200, 425))

    assert response.status_code == 425


def test_error_messages_never_carry_the_access_token():
    session = _FakeSession([_FakeResponse(400, "nope")])
    client, _ = _client(session)

    with pytest.raises(AdsApiError) as raised:
        client.request("GET", "/x")

    assert "cached-token" not in str(raised.value)

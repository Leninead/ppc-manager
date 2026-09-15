"""_Rest additions for sync jobs: RPC calls and inserts that answer back. No network."""
from __future__ import annotations

import json

import pytest
import requests

from core.integrations import store
from core.integrations.store import StoreError, _Rest


class _FakeResponse:
    def __init__(self, status_code: int = 200, body=None, content: bytes | None = None):
        self.status_code = status_code
        if content is None:
            content = b"" if body is None else json.dumps(body).encode()
        self.content = content

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)


class _FakeSession:
    def __init__(self, *responses: _FakeResponse):
        self._responses = list(responses)
        self.posts: list[dict] = []

    def post(self, url, json=None, params=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "params": params, "headers": headers,
                           "timeout": timeout})
        return self._responses.pop(0)


def _rest(*responses: _FakeResponse) -> tuple[_Rest, _FakeSession]:
    session = _FakeSession(*responses)
    return _Rest("http://rest-gateway", "jwt-for-tests", session=session), session


def test_rpc_posts_named_function_with_json_args():
    rest, session = _rest(_FakeResponse(body=[{"id": 1}]))

    answer = rest.rpc("claim_sync_jobs", {"p_holder": "w1", "p_limit": 5, "p_lease_seconds": 900})

    call = session.posts[0]
    assert call["url"] == "http://rest-gateway/rest/v1/rpc/claim_sync_jobs"
    assert call["json"] == {"p_holder": "w1", "p_limit": 5, "p_lease_seconds": 900}
    assert call["headers"]["Accept"] == "application/json"
    assert call["headers"]["Authorization"] == "Bearer jwt-for-tests"
    assert "Prefer" not in call["headers"]
    assert call["timeout"] == store._TIMEOUT_S
    assert answer == [{"id": 1}]


def test_rpc_returns_scalars_as_parsed_json():
    rest, _ = _rest(_FakeResponse(body=3), _FakeResponse(body=True), _FakeResponse(content=b"null"))

    assert rest.rpc("replace_search_term_day", {}) == 3
    assert rest.rpc("cancel_sync_job", {}) is True
    assert rest.rpc("retry_sync_job", {}) is None


def test_rpc_with_empty_body_returns_none():
    rest, _ = _rest(_FakeResponse(status_code=204))
    assert rest.rpc("anything", {}) is None


def test_rpc_accepts_a_longer_timeout_per_call():
    rest, session = _rest(_FakeResponse(body=0))
    rest.rpc("replace_search_term_day", {}, timeout_s=120)
    assert session.posts[0]["timeout"] == 120


def test_rpc_raises_on_http_error():
    rest, _ = _rest(_FakeResponse(status_code=404, body={"code": "PGRST202"}))
    with pytest.raises(requests.HTTPError):
        rest.rpc("missing_function", {})


def test_rpc_csv_asks_for_csv_and_returns_bytes():
    csv_body = b"campaign_id,search_term\n1,shoes\n"
    rest, session = _rest(_FakeResponse(content=csv_body))

    answer = rest.rpc_csv("search_terms_between", {"p_profile_id": "p1"}, timeout_s=120)

    call = session.posts[0]
    assert call["url"].endswith("/rpc/search_terms_between")
    assert call["headers"]["Accept"] == "text/csv"
    assert call["timeout"] == 120
    assert answer == csv_body


def test_insert_ignore_reports_inserted_row():
    rest, session = _rest(_FakeResponse(status_code=201, body=[{"id": 7}]))

    assert rest.insert_ignore("integration_sync_jobs", {"dedupe_key": "k"}, "dedupe_key") is True

    call = session.posts[0]
    assert call["url"] == "http://rest-gateway/rest/v1/integration_sync_jobs"
    assert call["params"] == {"on_conflict": "dedupe_key"}
    assert call["headers"]["Prefer"] == "return=representation,resolution=ignore-duplicates"
    assert call["json"] == {"dedupe_key": "k"}


def test_insert_ignore_reports_duplicate_as_false():
    rest, _ = _rest(_FakeResponse(status_code=201, body=[]))
    assert rest.insert_ignore("integration_sync_jobs", {"dedupe_key": "k"}, "dedupe_key") is False


def test_insert_returning_gives_back_the_stored_row():
    rest, session = _rest(_FakeResponse(status_code=201, body=[{"id": 9, "status": "to_request"}]))

    row = rest.insert_returning("ads_report_requests", {"job_id": 1})

    assert row == {"id": 9, "status": "to_request"}
    assert session.posts[0]["headers"]["Prefer"] == "return=representation"


def test_insert_returning_without_a_row_is_an_error():
    rest, _ = _rest(_FakeResponse(status_code=201, body=[]))
    with pytest.raises(StoreError):
        rest.insert_returning("ads_report_requests", {"job_id": 1})

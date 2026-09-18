"""ReportFetcher: create body, 425 duplicate reuse, status parsing and streamed download. No network."""
from __future__ import annotations

import io
import json
from datetime import date

import pytest
import requests

from core.amazon_ads.api_client import AdsApiClient, AdsApiError
from core.amazon_ads.product_rows import SB_LEGACY_CAMPAIGN_SPEC
from core.amazon_ads.report_fetcher import (
    CREATE_CONTENT_TYPE,
    REPORT_COLUMNS,
    DuplicateWithoutId,
    ReportFailed,
    ReportFetcher,
    SbV2ReportFetcher,
    parse_duplicate_report_id,
)

DUPLICATE_ID = "7df1ef5d-45ba-40cc-b607-ff2148cf4f5e"
DUPLICATE_BODY = {"code": "425", "detail": f"The Request is a duplicate of : {DUPLICATE_ID}"}
PRESIGNED_URL = "https://offline-report-storage.s3.amazonaws.com/report.json.gz?X-Amz-Signature=secret-signature"


class _FakeResponse:
    def __init__(self, status_code: int, body=None, chunks=(), chunk_error: Exception | None = None):
        self.status_code = status_code
        self.headers = {}
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body if body is not None else {})
        self._chunks = list(chunks)
        self._chunk_error = chunk_error
        self.closed = False
        self.chunk_sizes = []

    def json(self):
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body

    def iter_content(self, chunk_size):
        self.chunk_sizes.append(chunk_size)
        yield from self._chunks
        if self._chunk_error:
            raise self._chunk_error

    def close(self):
        self.closed = True


class _FakeApiSession:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": json})
        return self._outcomes.pop(0)


class _FakeDownloadSession:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _fetcher(api_outcomes=(), download_outcome=None):
    api_session = _FakeApiSession(api_outcomes)
    api = AdsApiClient(region="NA", client_id="client-abc", token_source=lambda force: "token",
                       session=api_session, sleep=lambda seconds: None)
    download_session = _FakeDownloadSession(download_outcome)
    return ReportFetcher(api, session=download_session), api_session, download_session


def test_create_posts_daily_search_term_configuration():
    fetcher, api_session, _ = _fetcher([_FakeResponse(200, {"reportId": "r-123", "status": "PENDING"})])

    report_id = fetcher.create("555", date(2026, 9, 1), date(2026, 9, 14))

    assert report_id == "r-123"
    call = api_session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/reporting/reports")
    assert call["headers"]["Content-Type"] == CREATE_CONTENT_TYPE
    assert call["headers"]["Amazon-Advertising-API-Scope"] == "555"
    body = call["json"]
    assert body["startDate"] == "2026-09-01"
    assert body["endDate"] == "2026-09-14"
    configuration = body["configuration"]
    assert configuration["adProduct"] == "SPONSORED_PRODUCTS"
    assert configuration["reportTypeId"] == "spSearchTerm"
    assert configuration["groupBy"] == ["searchTerm"]
    assert configuration["timeUnit"] == "DAILY"
    assert configuration["format"] == "GZIP_JSON"
    assert configuration["columns"] == REPORT_COLUMNS


def test_the_spec_decides_the_report_so_one_fetcher_serves_the_campaign_grain_too():
    from core.amazon_ads.campaign_rows import CAMPAIGN_REPORT_SPEC

    api_session = _FakeApiSession([_FakeResponse(200, {"reportId": "r-456", "status": "PENDING"})])
    api = AdsApiClient(region="NA", client_id="client-abc", token_source=lambda force: "token",
                       session=api_session, sleep=lambda seconds: None)
    fetcher = ReportFetcher(api, session=_FakeDownloadSession(None), spec=CAMPAIGN_REPORT_SPEC)

    fetcher.create("555", date(2026, 9, 8), date(2026, 9, 14))

    configuration = api_session.calls[0]["json"]["configuration"]
    assert configuration["reportTypeId"] == "spCampaigns"
    assert configuration["groupBy"] == ["campaign"]
    assert configuration["timeUnit"] == "DAILY"
    assert "campaignId" in configuration["columns"] and "date" in configuration["columns"]


def test_the_spec_names_the_ad_product_so_sponsored_brands_and_display_share_the_fetcher():
    from core.amazon_ads.report_fetcher import ReportSpec

    spec = ReportSpec(report_type_id="sbCampaigns", group_by=("campaign",), columns=("date", "campaignId"),
                      ad_product="SPONSORED_BRANDS", retention_days=60)
    api_session = _FakeApiSession([_FakeResponse(200, {"reportId": "r-789", "status": "PENDING"})])
    api = AdsApiClient(region="NA", client_id="client-abc", token_source=lambda force: "token",
                       session=api_session, sleep=lambda seconds: None)

    ReportFetcher(api, session=_FakeDownloadSession(None), spec=spec).create("555", date(2026, 9, 8),
                                                                              date(2026, 9, 14))

    configuration = api_session.calls[0]["json"]["configuration"]
    assert (configuration["adProduct"], configuration["reportTypeId"]) == ("SPONSORED_BRANDS", "sbCampaigns")


def test_report_columns_carry_both_attribution_windows_and_ids():
    for column in ("date", "campaignId", "adGroupId", "keywordId", "keywordType", "campaignStatus",
                   "adKeywordStatus", "campaignBudgetCurrencyCode", "purchases7d", "sales7d",
                   "unitsSoldClicks7d", "purchases14d", "sales14d", "unitsSoldClicks14d"):
        assert column in REPORT_COLUMNS
    assert len(REPORT_COLUMNS) == len(set(REPORT_COLUMNS))


def test_create_accepts_http_202():
    fetcher, _, _ = _fetcher([_FakeResponse(202, {"reportId": "r-202"})])

    assert fetcher.create("1", date(2026, 9, 1), date(2026, 9, 1)) == "r-202"


def test_duplicate_report_reuses_pending_id_on_http_425():
    fetcher, _, _ = _fetcher([_FakeResponse(425, DUPLICATE_BODY)])

    assert fetcher.create("1", date(2026, 9, 1), date(2026, 9, 14)) == DUPLICATE_ID


def test_duplicate_report_reuses_pending_id_on_http_200_with_body_code_425():
    fetcher, _, _ = _fetcher([_FakeResponse(200, DUPLICATE_BODY)])

    assert fetcher.create("1", date(2026, 9, 1), date(2026, 9, 14)) == DUPLICATE_ID


def test_duplicate_without_id_raises():
    fetcher, _, _ = _fetcher([_FakeResponse(425, {"code": "425", "detail": "Duplicate request"})])

    with pytest.raises(DuplicateWithoutId):
        fetcher.create("1", date(2026, 9, 1), date(2026, 9, 14))


def test_create_without_report_id_is_an_api_error():
    fetcher, _, _ = _fetcher([_FakeResponse(200, {"status": "PENDING"})])

    with pytest.raises(AdsApiError):
        fetcher.create("1", date(2026, 9, 1), date(2026, 9, 14))


@pytest.mark.parametrize("start, end", [
    (date(2026, 9, 2), date(2026, 9, 1)),
    (date(2026, 8, 1), date(2026, 9, 1)),
])
def test_create_rejects_invalid_windows_before_calling_amazon(start, end):
    fetcher, api_session, _ = _fetcher([])

    with pytest.raises(ValueError):
        fetcher.create("1", start, end)

    assert api_session.calls == []


def test_create_accepts_the_maximum_31_day_window():
    fetcher, _, _ = _fetcher([_FakeResponse(200, {"reportId": "r-31"})])

    assert fetcher.create("1", date(2026, 8, 1), date(2026, 8, 31)) == "r-31"


@pytest.mark.parametrize("body, expected", [
    (json.dumps(DUPLICATE_BODY), DUPLICATE_ID),
    ("The Request is a duplicate of: 7DF1EF5D-45BA-40CC-B607-FF2148CF4F5E", "7DF1EF5D-45BA-40CC-B607-FF2148CF4F5E"),
    (f'{{"detail": "duplicate request", "reportId": "{DUPLICATE_ID}"}}', DUPLICATE_ID),
    ('{"code":"425","detail":"Duplicate request"}', None),
    ("", None),
])
def test_parse_duplicate_report_id_is_tolerant(body, expected):
    assert parse_duplicate_report_id(body) == expected


def test_status_parses_completed_report():
    fetcher, api_session, _ = _fetcher([_FakeResponse(200, {
        "reportId": "r-1", "status": "COMPLETED", "url": PRESIGNED_URL,
        "urlExpiresAt": "2026-09-14T10:00:00Z", "fileSize": 5120, "failureReason": None,
    })])

    status = fetcher.status("555", "r-1")

    assert status.report_id == "r-1"
    assert status.status == "COMPLETED"
    assert status.url == PRESIGNED_URL
    assert status.file_size == 5120
    assert status.failure_reason == ""
    call = api_session.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/reporting/reports/r-1")
    assert call["headers"]["Amazon-Advertising-API-Scope"] == "555"


def test_status_parses_failed_report_reason():
    fetcher, _, _ = _fetcher([_FakeResponse(200, {"reportId": "r-2", "status": "FAILED",
                                                  "failureReason": "Internal failure"})])

    status = fetcher.status("1", "r-2")

    assert status.status == "FAILED"
    assert status.failure_reason == "Internal failure"
    assert status.url == ""
    assert status.file_size is None


def test_status_without_status_field_is_an_api_error():
    fetcher, _, _ = _fetcher([_FakeResponse(200, {"reportId": "r-3"})])

    with pytest.raises(AdsApiError):
        fetcher.status("1", "r-3")


def test_download_streams_chunks_without_auth_headers():
    response = _FakeResponse(200, chunks=[b"\x1f\x8b", b"abc", b"", b"defg"])
    fetcher, _, download_session = _fetcher(download_outcome=response)
    target = io.BytesIO()

    written = fetcher.download(PRESIGNED_URL, target, chunk_bytes=4096)

    assert written == 9
    assert target.getvalue() == b"\x1f\x8babcdefg"
    call = download_session.calls[0]
    assert call["url"] == PRESIGNED_URL
    assert call["stream"] is True
    assert "headers" not in call
    assert response.chunk_sizes == [4096]
    assert response.closed


def test_download_forbidden_means_expired_url():
    response = _FakeResponse(403, "<Error>AccessDenied</Error>")
    fetcher, _, _ = _fetcher(download_outcome=response)

    with pytest.raises(ReportFailed, match="download url expired"):
        fetcher.download(PRESIGNED_URL, io.BytesIO())

    assert response.closed


def test_download_other_status_is_an_api_error():
    fetcher, _, _ = _fetcher(download_outcome=_FakeResponse(500, "oops"))

    with pytest.raises(AdsApiError) as raised:
        fetcher.download(PRESIGNED_URL, io.BytesIO())

    assert raised.value.status == 500


@pytest.mark.parametrize("download_outcome", [
    requests.ConnectionError(f"Max retries exceeded with url: {PRESIGNED_URL}"),
    _FakeResponse(200, chunks=[b"ab"], chunk_error=requests.ConnectionError(f"reset {PRESIGNED_URL}")),
])
def test_download_errors_never_expose_the_presigned_url(download_outcome):
    fetcher, _, _ = _fetcher(download_outcome=download_outcome)

    with pytest.raises(AdsApiError) as raised:
        fetcher.download(PRESIGNED_URL, io.BytesIO())

    assert "secret-signature" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


# ── SB's v2 campaign report ──────────────────────────────────────────────────────


class _FakeV2Session:
    """Answers the v2 calls in order and records whether each one asked not to follow a redirect."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": json, **kwargs})
        return self._outcomes.pop(0)


def _v2_fetcher(api_outcomes=()):
    session = _FakeV2Session(api_outcomes)
    api = AdsApiClient(region="NA", client_id="client-abc", token_source=lambda force: "token", session=session,
                       sleep=lambda seconds: None)
    return SbV2ReportFetcher(api, session=_FakeDownloadSession(None), spec=SB_LEGACY_CAMPAIGN_SPEC), session


def _redirect(location: str) -> _FakeResponse:
    response = _FakeResponse(307, {})
    response.headers["Location"] = location
    return response


def test_a_v2_report_asks_one_day_of_every_creative_type():
    fetcher, session = _v2_fetcher([_FakeResponse(202, {"reportId": "amzn1.clicksAPI.v1.p1.X", "status": "IN_PROGRESS"})])

    assert fetcher.create("555", date(2026, 9, 16), date(2026, 9, 16)) == "amzn1.clicksAPI.v1.p1.X"

    [call] = session.calls
    assert (call["method"], call["url"]) == ("POST", "https://advertising-api.amazon.com/v2/hsa/campaigns/report")
    assert call["json"] == {"reportDate": "20260916", "metrics": ",".join(SB_LEGACY_CAMPAIGN_SPEC.columns),
                            "creativeType": "all"}
    assert call["headers"]["Amazon-Advertising-API-Scope"] == "555"


def test_a_v2_report_is_never_asked_for_more_than_one_day():
    fetcher, session = _v2_fetcher()

    with pytest.raises(ValueError, match="one day"):
        fetcher.create("555", date(2026, 9, 15), date(2026, 9, 16))
    assert session.calls == []


def test_a_finished_v2_report_gives_the_file_behind_its_redirect_without_following_it():
    fetcher, session = _v2_fetcher([
        _FakeResponse(200, {"reportId": "R1", "status": "SUCCESS", "fileSize": 9334,
                            "location": "https://advertising-api.amazon.com/v2/reports/R1/download"}),
        _redirect(PRESIGNED_URL),
    ])

    status = fetcher.status("555", "R1")

    assert (status.status, status.url, status.file_size) == ("COMPLETED", PRESIGNED_URL, 9334)
    download = session.calls[1]
    assert download["url"] == "https://advertising-api.amazon.com/v2/reports/R1/download"
    # Followed by requests, the redirect would carry the Amazon headers to the file host.
    assert download["allow_redirects"] is False


@pytest.mark.parametrize("amazon_status, status", [("IN_PROGRESS", "PROCESSING"), ("FAILURE", "FAILED")])
def test_a_v2_status_reads_in_v3_words(amazon_status, status):
    fetcher, session = _v2_fetcher([_FakeResponse(200, {"reportId": "R1", "status": amazon_status,
                                                        "statusDetails": "Report generation failed"})])

    report = fetcher.status("555", "R1")

    assert (report.status, report.url) == (status, "")
    assert report.failure_reason == ("Report generation failed" if status == "FAILED" else "")
    assert len(session.calls) == 1

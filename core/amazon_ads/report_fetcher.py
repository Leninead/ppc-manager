"""Reporting v3 reports of any ad product: create, poll, download. What differs travels in a ReportSpec.

Plus Sponsored Brands' v2 campaign report, which answers the same three calls in its own way.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import BinaryIO

import requests

from core.amazon_ads.api_client import AdsApiClient, AdsApiError

log = logging.getLogger(__name__)

REPORT_TYPE_ID = "spSearchTerm"
AMAZON_MAX_RANGE_DAYS = 31
RETENTION_DAYS = 65
REPORTS_PATH = "/reporting/reports"
CREATE_CONTENT_TYPE = "application/vnd.createasyncreportrequest.v3+json"
REPORT_COLUMNS = [
    "date",
    "campaignId",
    "campaignName",
    "campaignStatus",
    "adGroupId",
    "adGroupName",
    "keywordId",
    "keyword",
    "keywordType",
    "matchType",
    "targeting",
    "adKeywordStatus",
    "portfolioId",
    "searchTerm",
    "campaignBudgetCurrencyCode",
    "impressions",
    "clicks",
    "cost",
    "purchases7d",
    "sales7d",
    "unitsSoldClicks7d",
    "purchases14d",
    "sales14d",
    "unitsSoldClicks14d",
]
DUPLICATE_STATUS = 425
DOWNLOAD_TIMEOUT_SECONDS = 300
SB_V2_REPORT_PATH = "/v2/hsa/campaigns/report"
V2_REPORTS_PATH = "/v2/reports"
# v2's statuses in the words the worker already reads from v3.
_V2_STATUSES = {"SUCCESS": "COMPLETED", "IN_PROGRESS": "PROCESSING", "FAILURE": "FAILED"}
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


@dataclass(frozen=True)
class ReportSpec:
    """What makes one Reporting v3 report differ from another; creating and polling are the same."""

    report_type_id: str
    group_by: tuple[str, ...]
    columns: tuple[str, ...]
    time_unit: str = "DAILY"
    ad_product: str = "SPONSORED_PRODUCTS"
    # How far back Amazon keeps this report's data. It differs by ad product: 60 days for Sponsored Brands.
    retention_days: int = RETENTION_DAYS


SEARCH_TERM_SPEC = ReportSpec(
    report_type_id=REPORT_TYPE_ID,
    group_by=("searchTerm",),
    columns=tuple(REPORT_COLUMNS),
)

_DUPLICATE_OF_RE = re.compile(r"duplicate\s+of\s*:?\s*([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})")
_ANY_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


class ReportFailed(RuntimeError):
    """Amazon will not deliver this report: it failed, or its download link died."""

    def __init__(self, message: str, *, amazon_status: str = ""):
        super().__init__(message)
        self.amazon_status = amazon_status


class DuplicateWithoutId(RuntimeError):
    """Amazon said the request duplicates one in flight but did not say which."""


@dataclass(frozen=True)
class ReportStatus:
    report_id: str
    status: str
    url: str
    failure_reason: str
    file_size: int | None


class ReportFetcher:
    def __init__(self, api: AdsApiClient, *, session: requests.Session | None = None,
                 spec: ReportSpec = SEARCH_TERM_SPEC):
        self._api = api
        self._download_session = session or requests.Session()
        self._spec = spec

    def create(self, profile_id: str, start: date, end: date) -> str:
        if end < start:
            raise ValueError(f"report window ends before it starts: {start}..{end}")
        if (end - start).days + 1 > AMAZON_MAX_RANGE_DAYS:
            raise ValueError(f"report window {start}..{end} is longer than {AMAZON_MAX_RANGE_DAYS} days")

        response = self._api.request(
            "POST",
            REPORTS_PATH,
            profile_id=profile_id,
            json_body=_create_body(self._spec, start, end),
            content_type=CREATE_CONTENT_TYPE,
            expected=(200, 202, DUPLICATE_STATUS),
        )
        body = _json_object(response)
        if response.status_code == DUPLICATE_STATUS or str(body.get("code", "")) == str(DUPLICATE_STATUS):
            duplicate_id = parse_duplicate_report_id(response.text or "")
            if not duplicate_id:
                raise DuplicateWithoutId(f"profile {profile_id} {start}..{end}: duplicate without a report id")
            log.info("amazon_ads: profile %s %s..%s duplicates report %s, reusing it",
                     profile_id, start, end, duplicate_id)
            return duplicate_id

        report_id = str(body.get("reportId") or "").strip()
        if not report_id:
            raise AdsApiError(f"create report for profile {profile_id} returned no reportId",
                              status=response.status_code, body=(response.text or "")[:2000])
        log.info("amazon_ads: profile %s %s..%s report %s created", profile_id, start, end, report_id)
        return report_id

    def status(self, profile_id: str, report_id: str) -> ReportStatus:
        response = self._api.request("GET", f"{REPORTS_PATH}/{report_id}", profile_id=profile_id)
        body = _json_object(response)
        status = str(body.get("status") or "").strip().upper()
        if not status:
            raise AdsApiError(f"report {report_id} status response has no status",
                              status=response.status_code, body=(response.text or "")[:2000])
        file_size = body.get("fileSize")
        return ReportStatus(
            report_id=str(body.get("reportId") or report_id),
            status=status,
            url=str(body.get("url") or ""),
            failure_reason=str(body.get("failureReason") or ""),
            file_size=int(file_size) if isinstance(file_size, (int, float)) else None,
        )

    def download(self, url: str, target: BinaryIO, chunk_bytes: int = 1 << 20) -> int:
        # The presigned query string is a credential: `from None` keeps it out of chained tracebacks.
        try:
            response = self._download_session.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise AdsApiError(f"report download failed to start ({type(exc).__name__})") from None
        try:
            if response.status_code == 403:
                raise ReportFailed("download url expired")
            if response.status_code != 200:
                raise AdsApiError(f"report download -> HTTP {response.status_code}", status=response.status_code)
            written = 0
            for chunk in response.iter_content(chunk_size=chunk_bytes):
                if chunk:
                    target.write(chunk)
                    written += len(chunk)
            return written
        except requests.RequestException as exc:
            raise AdsApiError(f"report download interrupted ({type(exc).__name__})") from None
        finally:
            response.close()


class SbV2ReportFetcher(ReportFetcher):
    """Sponsored Brands' v2 campaign report, the only one with the campaigns v3 leaves out while in preview
    (isMultiAdGroupsEnabled = false). One day per report; creativeType "all" brings video and the rest."""

    def create(self, profile_id: str, start: date, end: date) -> str:
        if start != end:
            raise ValueError(f"a v2 report covers one day, not {start}..{end}")
        response = self._api.request(
            "POST",
            SB_V2_REPORT_PATH,
            profile_id=profile_id,
            json_body={"reportDate": start.strftime("%Y%m%d"), "metrics": ",".join(self._spec.columns),
                       "creativeType": "all"},
            content_type="application/json",
            expected=(200, 202),
        )
        report_id = str(_json_object(response).get("reportId") or "").strip()
        if not report_id:
            raise AdsApiError(f"create v2 report for profile {profile_id} returned no reportId",
                              status=response.status_code, body=(response.text or "")[:2000])
        log.info("amazon_ads: profile %s %s v2 report %s created", profile_id, start, report_id)
        return report_id

    def status(self, profile_id: str, report_id: str) -> ReportStatus:
        response = self._api.request("GET", f"{V2_REPORTS_PATH}/{report_id}", profile_id=profile_id)
        body = _json_object(response)
        raw_status = str(body.get("status") or "").strip().upper()
        if not raw_status:
            raise AdsApiError(f"v2 report {report_id} status response has no status",
                              status=response.status_code, body=(response.text or "")[:2000])
        status = _V2_STATUSES.get(raw_status, raw_status)
        file_size = body.get("fileSize")
        return ReportStatus(
            report_id=report_id,
            status=status,
            url=self._file_url(profile_id, report_id) if status == "COMPLETED" else "",
            failure_reason=str(body.get("statusDetails") or "") if status == "FAILED" else "",
            file_size=int(file_size) if isinstance(file_size, (int, float)) else None,
        )

    def _file_url(self, profile_id: str, report_id: str) -> str:
        # The download answers with a redirect to a presigned file, which `download` reads without credentials.
        response = self._api.request("GET", f"{V2_REPORTS_PATH}/{report_id}/download", profile_id=profile_id,
                                     expected=_REDIRECT_STATUSES, allow_redirects=False)
        location = str((response.headers or {}).get("Location") or "")
        if not location:
            raise AdsApiError(f"v2 report {report_id} download gave no location", status=response.status_code)
        return location


def parse_duplicate_report_id(body: str) -> str | None:
    """The in-flight report id from a 425 body; the format is community-observed, so any UUID is accepted."""
    if not body:
        return None
    duplicate_of = _DUPLICATE_OF_RE.search(body)
    if duplicate_of:
        return duplicate_of.group(1)
    any_uuid = _ANY_UUID_RE.search(body)
    return any_uuid.group(0) if any_uuid else None


def _create_body(spec: ReportSpec, start: date, end: date) -> dict:
    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "configuration": {
            "adProduct": spec.ad_product,
            "reportTypeId": spec.report_type_id,
            "groupBy": list(spec.group_by),
            "columns": list(spec.columns),
            "timeUnit": spec.time_unit,
            "format": "GZIP_JSON",
        },
    }


def _json_object(response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}

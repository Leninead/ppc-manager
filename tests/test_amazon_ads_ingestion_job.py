"""IngestionJob tick over an in-memory PostgREST and a fake Amazon at the HTTP layer. No network.

The fake database emulates the claim, retry and empty-day functions of migration 009;
the fake Amazon answers Reporting v3, portfolios and the report download host.
"""
from __future__ import annotations

import copy
import fnmatch
import functools
import gzip
import json
import tracemalloc
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

import pytest
import requests

from core.amazon_ads import ingestion_job as ingestion_module
from core.amazon_ads.api_client import CLIENT_ID_HEADER, AdsApiClient
from core.amazon_ads.ingestion_job import (
    NO_CAMPAIGN_ACCESS_WARNING,
    NO_PORTFOLIO_ACCESS_WARNING,
    NO_SB_ACCESS_WARNING,
    PROFILE_INACTIVE_REASON,
    SAVE_CRASHED_MESSAGE,
    IngestionJob,
    TickSummary,
    _profile_state,
    _Tick,
)
from core.amazon_ads import report_kinds
from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    CAMPAIGNS_KIND,
    PRODUCT_KINDS,
    SB_CAMPAIGNS_KIND,
    SB_ENTITIES_KIND,
    SB_LEGACY_KIND,
    SB_TARGETING_KIND,
    SD_CAMPAIGNS_KIND,
    SD_ENTITIES_KIND,
    SP_PRODUCT_ADS_KIND,
    SP_TARGETING_KIND,
    SP_TARGETS_KIND,
)
from core.integrations import oauth
from core.integrations.sync_jobs import OPEN_STATUSES, SyncJobStore

NOW = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)  # Monday 10:00 in Los Angeles
YESTERDAY = "2026-09-13"
JOBS = "integration_sync_jobs"
REQUESTS = "ads_report_requests"
PROFILES = "ads_profile_sync"
DAILY_ROWS = "ads_search_term_daily"
CAMPAIGN_DAILY = "ads_campaign_daily"
CAMPAIGNS = "ads_campaign"
TARGETS = "ads_target"
TARGET_DAILY = "ads_target_daily"
PRODUCT_CAMPAIGNS = "ads_sb_sd_campaign"
PRODUCT_CAMPAIGN_DAILY = "ads_sb_sd_campaign_daily"
HEARTBEATS = "integration_worker_heartbeats"
NEW_TABLES = {JOBS, REQUESTS, PROFILES, DAILY_ROWS, "ads_portfolios", HEARTBEATS}


@pytest.fixture(autouse=True)
def _without_product_jobs(request, monkeypatch):
    """Most of this suite is about search terms and SP campaigns, and every count it asserts would change with
    the targeting and SB / SD jobs planned on the same ticks. The tests about those ask for `with_products`."""
    if "with_products" in request.fixturenames:
        return
    real_plan = ingestion_module.plan_jobs
    monkeypatch.setattr(ingestion_module, "plan_jobs", lambda state, now: [
        job for job in real_plan(state, now) if job.job_kind not in PRODUCT_KINDS])


@pytest.fixture
def with_products():
    """Plan the targeting and SB / SD jobs too, as production does."""


def _defaults(table: str, stamp: str) -> dict:
    if table == JOBS:
        return {
            "account_id": None, "connection_id": None, "external_account_id": "", "cliente": "", "account_name": "",
            "marketplace": "", "region": "", "window_start": None, "window_end": None, "local_day": None,
            "status": "pending", "phase": "", "attempts": 0, "max_attempts": 8, "next_attempt_at": stamp,
            "lease_holder": "", "lease_expires_at": None, "rows_written": None, "warning": "", "error_class": "",
            "error_message": "", "attempt_log": [], "requested_by": "scheduler", "retry_of": None, "dedupe_key": None,
            "created_at": stamp, "started_at": None, "finished_at": None, "updated_at": stamp,
        }
    if table == REQUESTS:
        return {
            "status": "to_request", "report_kind": "search_terms",
            "amazon_report_id": "", "amazon_status": "", "requested_at": None,
            "next_poll_at": None, "poll_count": 0, "save_attempts": 0, "lease_holder": "", "lease_expires_at": None,
            "row_count": None,
            "skipped_days": [], "error_class": "", "error_message": "", "raw_status": "none", "raw_path": "",
            "raw_bytes": None, "raw_sha256": "", "raw_pruned_at": None, "saved_at": None, "created_at": stamp,
            "updated_at": stamp,
        }
    if table == PROFILES:
        return {
            "account_id": None, "connection_id": None, "cliente": "", "account_name": "", "account_type": "",
            "region": "", "country_code": "", "currency_code": "", "timezone": "", "access": "", "status": "active",
            "backfill_done_at": None, "data_from": None, "data_through": None, "refreshed_on": None,
            "last_success_at": None, "last_failure_at": None, "last_error": "", "updated_at": stamp,
        }
    return {}


def _comparable(raw):
    if isinstance(raw, (int, float)):
        return raw
    text = str(raw)
    if len(text) == 10:
        return datetime.combine(date.fromisoformat(text), time.min, tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _matches(row: dict, params: dict) -> bool:
    for column, expression in params.items():
        if column in ("select", "order", "limit"):
            continue
        operator, _, operand = expression.partition(".")
        value = row.get(column)
        if operator == "eq":
            matched = value is not None and str(value) == operand
        elif operator == "in":
            matched = value is not None and str(value) in operand.strip("()").split(",")
        elif operator == "like":
            matched = value is not None and fnmatch.fnmatchcase(str(value), operand.replace("%", "*"))
        elif operator in ("lt", "lte", "gt", "gte"):
            if value is None:
                return False
            left, right = _comparable(value), _comparable(operand)
            matched = {"lt": left < right, "lte": left <= right, "gt": left > right, "gte": left >= right}[operator]
        elif operator == "is":
            matched = {"false": value is False, "true": value is True, "null": value is None}[operand]
        else:
            raise AssertionError(f"the fake PostgREST does not support {column}={expression}")
        if not matched:
            return False
    return True


def _is_day(row: dict, profile_id: str, ad_product: str, day: str, source: str | None) -> bool:
    """A row of that profile, product and day, and of that source when one is given."""
    return ((row["profile_id"], row["ad_product"], row["report_date"]) == (profile_id, ad_product, day)
            and (source is None or row.get("source", "v3") == source))


class _WorkerKilled(BaseException):
    """Stands in for an out-of-memory kill or SIGKILL: nothing in the worker may catch it."""


class _FakePostgrest:
    def __init__(self, now: datetime):
        self.now = now
        self.tables: dict[str, list[dict]] = defaultdict(list)
        self.missing_tables: set[str] = set()
        self.replaced_days: list[str] = []
        self.campaign_days: list[str] = []
        self.rpc_timeouts: dict[str, int] = {}
        self._armed_failures: list[tuple[str, str, object, BaseException]] = []

    def fail_once(self, operation: str, table: str, when=lambda call: True, error: BaseException | None = None):
        """The next `operation` ('select', 'update' or 'rpc') on `table` matching `when` raises `error`."""
        failure = error or requests.ConnectionError(f"rest-gateway dropped the {operation} on {table}")
        self._armed_failures.append((operation, table, when, failure))

    def seed(self, table: str, **row) -> dict:
        return self._append(table, row)

    def rows(self, table: str, **equals) -> list[dict]:
        return [row for row in self.tables[table] if all(row.get(key) == value for key, value in equals.items())]

    def select(self, table, params):
        self._require(table)
        self._raise_if_armed("select", table, params)
        found = [row for row in self.tables[table] if _matches(row, params)]
        for part in reversed(params.get("order", "").split(",") if params.get("order") else []):
            column, _, direction = part.partition(".")
            found.sort(key=lambda row: _comparable(row[column]), reverse=direction == "desc")
        if "limit" in params:
            found = found[:int(params["limit"])]
        return copy.deepcopy(found)

    def insert(self, table, rows):
        self._require(table)
        for row in rows if isinstance(rows, list) else [rows]:
            self._append(table, row)

    def insert_ignore(self, table, row, on_conflict, *, timeout_s=8):
        self._require(table)
        key = row.get(on_conflict)
        if key is not None and any(existing.get(on_conflict) == key for existing in self.tables[table]):
            return False
        self._append(table, row)
        return True

    def upsert(self, table, rows, on_conflict=None):
        self._require(table)
        key_columns = on_conflict.split(",")
        for row in rows if isinstance(rows, list) else [rows]:
            existing = next((current for current in self.tables[table]
                             if all(current.get(column) == row.get(column) for column in key_columns)), None)
            if existing is None:
                self._append(table, row)
            else:
                existing.update(copy.deepcopy(row))

    def update(self, table, params, changes, stamp=True):
        self._require(table)
        self._raise_if_armed("update", table, {"params": params, "changes": changes})
        for row in self.tables[table]:
            if _matches(row, params):
                row.update(copy.deepcopy(changes))

    def rpc(self, name, args, *, timeout_s=8):
        self.rpc_timeouts[name] = timeout_s
        self._raise_if_armed("rpc", name, args)
        return getattr(self, f"_{name}")(**args)

    def _raise_if_armed(self, operation: str, table: str, call) -> None:
        for armed in self._armed_failures:
            armed_operation, armed_table, when, failure = armed
            if (armed_operation, armed_table) == (operation, table) and when(call):
                self._armed_failures.remove(armed)
                raise failure

    def _claim_sync_jobs(self, p_holder, p_limit, p_lease_seconds):
        self._require(JOBS)

        def is_due(job):
            before_deadline = self.now < _comparable(job["deadline_at"])
            if job["status"] in ("pending", "retrying"):
                return _comparable(job["next_attempt_at"]) <= self.now and before_deadline
            # 009: a lapsed lease in any phase means the worker died mid-job.
            return (job["status"] == "running" and job["lease_expires_at"] is not None
                    and _comparable(job["lease_expires_at"]) < self.now and before_deadline)

        priority = {"manual": 0, "retry": 0, "backfill": 1}
        due_jobs = sorted((job for job in self.tables[JOBS] if is_due(job)),
                          key=lambda job: (priority.get(job["trigger"], 2), _comparable(job["next_attempt_at"])))
        for job in due_jobs[:p_limit]:
            job.update(status="running", lease_holder=p_holder,
                       lease_expires_at=(self.now + timedelta(seconds=p_lease_seconds)).isoformat(),
                       started_at=job["started_at"] or self.now.isoformat())
        return copy.deepcopy(due_jobs[:p_limit])

    def _claim_report_requests(self, p_holder, p_statuses, p_kinds, p_limit, p_lease_seconds):
        self._require(REQUESTS)

        def is_due(request):
            lease_free = (request["lease_holder"] == "" or request["lease_expires_at"] is None
                          or _comparable(request["lease_expires_at"]) < self.now)
            poll_due = (request["status"] != "requested" or request["next_poll_at"] is None
                        or _comparable(request["next_poll_at"]) <= self.now)
            return (request["status"] in p_statuses and request["report_kind"] in p_kinds
                    and lease_free and poll_due)

        due_requests = sorted((request for request in self.tables[REQUESTS] if is_due(request)),
                              key=lambda request: (_comparable(request["created_at"]), request["id"]))[:p_limit]
        for request in due_requests:
            request.update(lease_holder=p_holder,
                           lease_expires_at=(self.now + timedelta(seconds=p_lease_seconds)).isoformat())
        return copy.deepcopy(due_requests)

    def _retry_sync_job(self, p_job_id, p_actor):
        failed_job = next((job for job in self.tables[JOBS] if job["id"] == p_job_id), None)
        if failed_job is None or failed_job["status"] not in ("failed", "cancelled"):
            return None
        is_amazon = failed_job["integration_slug"] == "amazon_ads"
        profile = next((row for row in self.tables[PROFILES]
                        if is_amazon and row["profile_id"] == failed_job["external_account_id"]), None)
        if is_amazon and (profile is None or profile["status"] != "active"):
            return None
        if any(job["retry_of"] == p_job_id and job["status"] in ("pending", "running", "retrying")
               for job in self.tables[JOBS]):
            return None
        current = profile or {}
        retry = self._append(JOBS, {
            **{column: failed_job[column] for column in (
                "integration_slug", "job_kind", "external_account_id", "window_start", "window_end", "local_day",
                "max_attempts")},
            "trigger": "retry",
            "account_id": current["account_id"] if profile else failed_job["account_id"],
            "connection_id": current["connection_id"] if profile else failed_job["connection_id"],
            "cliente": current.get("cliente") or failed_job["cliente"],
            "account_name": current.get("account_name") or failed_job["account_name"],
            "marketplace": current.get("country_code") or failed_job["marketplace"],
            "region": current.get("region") or failed_job["region"],
            "next_attempt_at": self.now.isoformat(),
            "deadline_at": (self.now + timedelta(hours=6)).isoformat(),
            "requested_by": p_actor or "app",
            "retry_of": p_job_id,
        })
        return retry["id"]

    def _replace_search_term_day(self, p_profile_id, p_day, p_rows):
        self._require(DAILY_ROWS)
        self.replaced_days.append(p_day)

        def is_that_day(row):
            return row["profile_id"] == p_profile_id and row["report_date"] == p_day

        if not p_rows:
            return -1 if any(is_that_day(row) for row in self.tables[DAILY_ROWS]) else 0
        self.tables[DAILY_ROWS] = [row for row in self.tables[DAILY_ROWS] if not is_that_day(row)]
        self.tables[DAILY_ROWS].extend({**row, "profile_id": p_profile_id, "report_date": p_day} for row in p_rows)
        return len(p_rows)

    def _replace_campaign_day(self, p_profile_id, p_day, p_rows):
        self._require(CAMPAIGN_DAILY)
        self.campaign_days.append(p_day)

        def is_that_day(row):
            return row["profile_id"] == p_profile_id and row["report_date"] == p_day

        if not p_rows:
            return -1 if any(is_that_day(row) for row in self.tables[CAMPAIGN_DAILY]) else 0
        self.tables[CAMPAIGN_DAILY] = [row for row in self.tables[CAMPAIGN_DAILY] if not is_that_day(row)]
        self.tables[CAMPAIGN_DAILY].extend({**row, "profile_id": p_profile_id, "report_date": p_day}
                                           for row in p_rows)
        return len(p_rows)

    def _replace_target_day(self, p_profile_id, p_ad_product, p_day, p_rows):
        return self._replace_product_day(TARGET_DAILY, p_profile_id, p_ad_product, p_day, p_rows)

    def _replace_sb_sd_campaign_day(self, p_profile_id, p_ad_product, p_day, p_rows, p_source="v3"):
        if p_source == "v2" and p_rows:
            # 015: from v2 only the old-format SB campaigns enter; v3 already has the rest. A payload left
            # with none still clears the day's v2 rows, as the SQL deletes before it inserts nothing.
            legacy = {row["campaign_id"] for row in self.tables[PRODUCT_CAMPAIGNS]
                      if row.get("ad_product") == "SB" and row.get("is_multi_ad_groups") is False}
            p_rows = [row for row in p_rows if row["campaign_id"] in legacy]
            if not p_rows:
                self.tables[PRODUCT_CAMPAIGN_DAILY] = [
                    row for row in self.tables[PRODUCT_CAMPAIGN_DAILY]
                    if not _is_day(row, p_profile_id, p_ad_product, p_day, p_source)]
                return 0
        return self._replace_product_day(PRODUCT_CAMPAIGN_DAILY, p_profile_id, p_ad_product, p_day, p_rows,
                                         source=p_source)

    def _replace_product_day(self, table, p_profile_id, p_ad_product, p_day, p_rows, *, source=None):
        # 015: the day is replaced for one ad product only, never for the others of the same profile, and for
        # one source only: v2 never erases v3's rows of the day, nor v3 v2's.
        self._require(table)

        def is_that_day(row):
            return _is_day(row, p_profile_id, p_ad_product, p_day, source)

        if not p_rows:
            return -1 if any(is_that_day(row) for row in self.tables[table]) else 0
        self.tables[table] = [row for row in self.tables[table] if not is_that_day(row)]
        self.tables[table].extend({**row, "profile_id": p_profile_id, "ad_product": p_ad_product,
                                   "report_date": p_day, **({"source": source} if source else {})} for row in p_rows)
        return len(p_rows)

    def _append(self, table: str, row: dict) -> dict:
        full_row = {**_defaults(table, self.now.isoformat()), **copy.deepcopy(row)}
        if table in (JOBS, REQUESTS) and "id" not in full_row:
            full_row["id"] = max((existing["id"] for existing in self.tables[table]), default=0) + 1
        self.tables[table].append(full_row)
        return full_row

    def _require(self, table: str) -> None:
        if table in self.missing_tables:
            response = requests.Response()
            response.status_code = 404
            raise requests.HTTPError(f"404 Client Error: Not Found for url: http://rest-gateway/rest/v1/{table}",
                                     response=response)


class _FakeResponse:
    def __init__(self, status_code: int, body=None, chunks=()):
        self.status_code = status_code
        self.headers = {}
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)
        self._chunks = list(chunks)

    def json(self):
        return self._body

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        pass


class _FakeAmazon:
    REPORTS_HOST = "https://reports.fake-amazon.test"

    def __init__(self, rows_per_day: int = 2, campaign_rows_per_day: int = 0):
        self.rows_per_day = rows_per_day
        self.campaign_rows_per_day = campaign_rows_per_day
        self.reports: dict[str, dict] = {}
        self.create_outcomes: list[_FakeResponse] = []
        self.status_scripts: list[list[str]] = []
        self.portfolio_outcome = _FakeResponse(200, {"portfolios": [
            {"portfolioId": 444, "name": "Brand Portfolio", "state": "ENABLED"}]})
        self.campaign_outcome = _FakeResponse(200, {"campaigns": [
            {"campaignId": 909, "name": "Demo - SP - KW - EXACT", "state": "ENABLED",
             "targetingType": "MANUAL", "startDate": "2026-03-21",
             "budget": {"budget": 15.0, "budgetType": "DAILY"},
             "dynamicBidding": {"strategy": "MANUAL"}, "portfolioId": 444}]})
        # Targeting and SB / SD lists answer empty unless a test fills them, so they stay out of the way.
        self.sp_keywords: list[dict] = []
        self.sp_targets: list[dict] = []
        self.sp_product_ads: list[dict] = []
        self.sb_campaigns: list[dict] = []
        self.sd_campaigns: list[dict] = []
        self.sd_ad_groups: list[dict] = []
        self.sb_outcome: _FakeResponse | None = None
        self.product_report_rows: dict[str, list[dict]] = {}
        # SB's v2 campaign report, by day: it has no date field of its own.
        self.v2_rows_by_day: dict[str, list[dict]] = {}
        self.v2_creates: list[tuple[str, str, dict]] = []
        self.empty_days: set[str] = set()
        self.created: list[tuple[str, str, str]] = []
        self.campaign_creates: list[tuple[str, str, str]] = []
        self.product_creates: list[tuple[str, str, str, str]] = []
        self.create_attempts = 0
        self.client_ids: list[str] = []
        self.connections_used: list[tuple[str, int]] = []

    def add_report(self, profile_id: str, start: str, end: str, statuses=("COMPLETED",)) -> str:
        report_id = f"7df1ef5d-45ba-40cc-b607-{len(self.reports) + 1:012d}"
        self.reports[report_id] = {"profile_id": profile_id, "start": start, "end": end, "statuses": list(statuses)}
        return report_id

    def request(self, method, url, **kwargs):
        self.client_ids.append(kwargs["headers"][CLIENT_ID_HEADER])
        path = url.split("amazon.com", 1)[1]
        if (method, path) == ("POST", "/reporting/reports"):
            return self._create(kwargs["headers"], kwargs["json"])
        if method == "GET" and path.startswith("/reporting/reports/"):
            return self._status(path.rsplit("/", 1)[1])
        if (method, path) == ("POST", "/portfolios/list"):
            return self.portfolio_outcome
        if (method, path) == ("POST", "/sp/campaigns/list"):
            return self.campaign_outcome
        if (method, path) == ("POST", "/sp/keywords/list"):
            return _FakeResponse(200, {"keywords": self.sp_keywords, "totalResults": len(self.sp_keywords)})
        if (method, path) == ("POST", "/sp/targets/list"):
            return _FakeResponse(200, {"targetingClauses": self.sp_targets, "totalResults": len(self.sp_targets)})
        if (method, path) == ("POST", "/sp/productAds/list"):
            return _FakeResponse(200, {"productAds": self.sp_product_ads, "totalResults": len(self.sp_product_ads)})
        if (method, path) == ("POST", "/sb/v4/campaigns/list"):
            return self.sb_outcome or _FakeResponse(200, {"campaigns": self.sb_campaigns})
        if method == "GET" and path.startswith(("/sb/keywords", "/sd/targets")):
            return _FakeResponse(200, [])
        if (method, path) in (("POST", "/sb/targets/list"), ("POST", "/sb/themes/list")):
            return _FakeResponse(200, {"targets": [], "themes": []})
        if method == "GET" and path.startswith(("/sd/campaigns", "/sd/adGroups")):
            start_index = int(path.split("startIndex=", 1)[1].split("&", 1)[0]) if "startIndex=" in path else 0
            listed = self.sd_campaigns if path.startswith("/sd/campaigns") else self.sd_ad_groups
            return _FakeResponse(200, listed if start_index == 0 else [])
        if (method, path) == ("POST", "/v2/hsa/campaigns/report"):
            return self._create_v2(kwargs["headers"], kwargs["json"])
        if method == "GET" and path.startswith("/v2/reports/"):
            return self._v2_status_or_file(path.removeprefix("/v2/reports/"), kwargs)
        raise AssertionError(f"unexpected Amazon call {method} {path}")

    def _create_v2(self, headers: dict, body: dict) -> _FakeResponse:
        profile_id = headers["Amazon-Advertising-API-Scope"]
        day = f"{body['reportDate'][:4]}-{body['reportDate'][4:6]}-{body['reportDate'][6:]}"
        self.v2_creates.append((profile_id, day, body))
        report_id = f"amzn1.clicksAPI.v1.p1.{len(self.reports) + 1:08d}"
        self.reports[report_id] = {"profile_id": profile_id, "start": day, "end": day, "statuses": ["SUCCESS"],
                                   "v2": True}
        return _FakeResponse(202, {"reportId": report_id, "recordType": "campaign", "status": "IN_PROGRESS"})

    def _v2_status_or_file(self, rest_of_path: str, kwargs: dict) -> _FakeResponse:
        report_id, _, action = rest_of_path.partition("/")
        if action == "download":
            # The file sits behind a redirect the client must not follow with its credentials.
            assert kwargs.get("allow_redirects") is False
            response = _FakeResponse(307)
            response.headers["Location"] = f"{self.REPORTS_HOST}/{report_id}.json.gz?X-Amz-Signature=test-signature"
            return response
        return _FakeResponse(200, {"reportId": report_id, "status": self.reports[report_id]["statuses"][0],
                                   "location": f"https://advertising-api.amazon.com/v2/reports/{report_id}/download"})

    def get(self, url, **kwargs):
        report_id = url.removeprefix(f"{self.REPORTS_HOST}/").split(".json.gz", 1)[0]
        body = gzip.compress(json.dumps(self._report_rows(self.reports[report_id])).encode("utf-8"))
        return _FakeResponse(200, chunks=[body[:50], body[50:]])

    def _create(self, headers: dict, body: dict) -> _FakeResponse:
        profile_id = headers["Amazon-Advertising-API-Scope"]
        window = (profile_id, body["startDate"], body["endDate"])
        report_type = body["configuration"]["reportTypeId"]
        if report_type not in ("spSearchTerm", "spCampaigns"):
            self.product_creates.append((report_type, *window))
            report_id = self.add_report(profile_id, body["startDate"], body["endDate"], ["COMPLETED"])
            self.reports[report_id]["product"] = report_type
            return _FakeResponse(200, {"reportId": report_id, "status": "PENDING"})
        # The campaign grain rides the same machinery; keeping its creates apart lets every
        # assertion below stay exhaustive over the search-term pipeline it is about.
        if report_type != "spSearchTerm":
            self.campaign_creates.append(window)
            report_id = self.add_report(profile_id, body["startDate"], body["endDate"], ["COMPLETED"])
            self.reports[report_id]["campaigns"] = True
            return _FakeResponse(200, {"reportId": report_id, "status": "PENDING"})
        self.create_attempts += 1
        if self.create_outcomes:
            return self.create_outcomes.pop(0)
        statuses = self.status_scripts.pop(0) if self.status_scripts else ["COMPLETED"]
        report_id = self.add_report(profile_id, body["startDate"], body["endDate"], statuses)
        self.created.append(window)
        return _FakeResponse(200, {"reportId": report_id, "status": "PENDING"})

    def _status(self, report_id: str) -> _FakeResponse:
        statuses = self.reports[report_id]["statuses"]
        status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
        body = {"reportId": report_id, "status": status}
        if status == "COMPLETED":
            body["url"] = f"{self.REPORTS_HOST}/{report_id}.json.gz?X-Amz-Signature=test-signature"
        if status == "FAILED":
            body["failureReason"] = "Report generation failed"
        return _FakeResponse(200, body)

    def _report_rows(self, report: dict) -> list[dict]:
        # Campaign reports are empty unless a test asks for rows, so they never reach the
        # search-term counts the rest of this suite asserts.
        if report.get("v2"):
            return self.v2_rows_by_day.get(report["start"], [])
        if report.get("product"):
            return [row for row in self.product_report_rows.get(report["product"], [])
                    if report["start"] <= row["date"] <= report["end"]]
        if report.get("campaigns"):
            return self._campaign_report_rows(report)
        first_day, last_day = date.fromisoformat(report["start"]), date.fromisoformat(report["end"])
        api_rows = []
        for offset in range((last_day - first_day).days + 1):
            day = (first_day + timedelta(days=offset)).isoformat()
            if day in self.empty_days:
                continue
            for index in range(self.rows_per_day):
                api_rows.append({
                    "date": day, "campaignId": 111, "campaignName": "Campaign A", "campaignStatus": "ENABLED",
                    "adGroupId": 222, "adGroupName": "Ad group A", "keywordId": 333 + index,
                    "keyword": f"keyword {index}", "keywordType": "BROAD", "matchType": "BROAD",
                    "targeting": f"keyword {index}", "adKeywordStatus": "ENABLED", "portfolioId": 444,
                    "searchTerm": f"search term {index}", "campaignBudgetCurrencyCode": "USD", "impressions": 100,
                    "clicks": 3, "cost": 1.5, "purchases7d": 1, "sales7d": 20.0, "unitsSoldClicks7d": 1,
                    "purchases14d": 1, "sales14d": 21.0, "unitsSoldClicks14d": 1,
                })
        return api_rows

    def _campaign_report_rows(self, report: dict) -> list[dict]:
        first_day, last_day = date.fromisoformat(report["start"]), date.fromisoformat(report["end"])
        return [
            {"date": (first_day + timedelta(days=offset)).isoformat(), "campaignId": 900 + index,
             "impressions": 50, "clicks": 2, "cost": 1.25, "purchases7d": 1, "sales7d": 15.0,
             "purchases14d": 1, "sales14d": 16.0, "campaignBudgetCurrencyCode": "USD"}
            for offset in range((last_day - first_day).days + 1)
            for index in range(self.campaign_rows_per_day)
        ]


def _search_term_requests(rest: _FakePostgrest, **filters) -> list[dict]:
    """The chunks of the search-term pipeline, which is what this suite is about.

    A tick now also queues the campaign grain's own chunks into the same table; selecting by kind
    keeps each assertion exhaustive over its own pipeline instead of counting the other one's rows.
    """
    return rest.rows(REQUESTS, report_kind=report_kinds.SEARCH_TERMS_REPORT, **filters)


def _connect_profile(rest: _FakePostgrest, profile_id: str = "1001", *, connection_id: int = 5,
                     connection_state: str = "activo", profile_row: dict | None = None) -> None:
    rest.seed("integration_connections", id=connection_id, integration_slug="amazon_ads", estado=connection_state)
    rest.seed("integration_accounts", id=connection_id + 100, integration_slug="amazon_ads",
              nombre_externo=f"Demo Seller {profile_id}", tipo="seller", region="NA", cliente=f"cliente-{profile_id}",
              connection_id=connection_id, profiles=[{
                  "profile_id": profile_id, "country_code": "US", "marketplace_id": "ATVPDKIKX0DER", "access": "edit",
                  "timezone": "America/Los_Angeles", "currency_code": "USD"}])
    if profile_row is not None:
        rest.seed(PROFILES, profile_id=profile_id, timezone="America/Los_Angeles", region="NA", **profile_row)


def _backfilled(**overrides) -> dict:
    return {"backfill_done_at": "2026-08-01T00:00:00+00:00", "refreshed_on": "2026-09-13", **overrides}


class _FakeTokens:
    def __init__(self):
        self.forgotten: list[int] = []

    def forget(self, connection_id: int) -> None:
        self.forgotten.append(connection_id)


class _RotatingCredentialTokens(_FakeTokens):
    """Every token request is a real refresh that reads the next client id, as after a credential swap."""

    def __init__(self, client_ids: list[str]):
        super().__init__()
        self._pending_client_ids = list(client_ids)
        self.current_client_id = self._pending_client_ids[0]

    def client_id(self) -> str:
        return self.current_client_id

    def token_source(self, connection_id: int):
        def access_token(force_refresh: bool) -> str:
            if self._pending_client_ids:
                self.current_client_id = self._pending_client_ids.pop(0)
            return f"token-for-{self.current_client_id}"

        return access_token


def _ingestion(rest: _FakePostgrest, amazon: _FakeAmazon, raw_dir, *, token_source=None, tokens=None, clock=None,
               **limits) -> IngestionJob:
    def api_factory(region: str, connection_id: int) -> AdsApiClient:
        amazon.connections_used.append((region, connection_id))
        return AdsApiClient(region=region, client_id="client-test",
                            token_source=token_source or (lambda force_refresh: "access-token"),
                            session=amazon, sleep=lambda seconds: None, max_retries=0)

    return IngestionJob(rest=rest, jobs=SyncJobStore(rest), tokens=tokens or _FakeTokens(), raw_dir=raw_dir,
                        holder="worker-test", api_factory=api_factory, download_session=amazon,
                        clock=clock or (lambda: rest.now), **limits)


def _tick(ingestion: IngestionJob, rest: _FakePostgrest, moment: datetime) -> TickSummary:
    rest.now = moment
    return ingestion.run_tick(moment)


def _only(rows: list[dict]) -> dict:
    assert len(rows) == 1, rows
    return rows[0]


def test_first_tick_backfills_five_chunks_then_saves_them_and_closes_the_job(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon(rows_per_day=2)
    _connect_profile(rest)
    ingestion = _ingestion(rest, amazon, tmp_path)

    first = _tick(ingestion, rest, NOW)

    assert first.errors == []
    assert (first.profiles_active, first.jobs_planned, first.reports_created, first.jobs_completed) == (1, 4, 8, 2)
    backfill = _only(rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms"))
    assert (backfill["status"], backfill["phase"]) == ("running", "waiting")
    windows = [(row["window_start"], row["window_end"]) for row in _search_term_requests(rest)]
    assert windows[0] == ("2026-08-31", YESTERDAY) and windows[-1] == ("2026-07-11", "2026-07-19")
    assert len(windows) == 5 and all(row["status"] == "requested" for row in _search_term_requests(rest))
    assert _only(rest.rows("ads_portfolios"))["name"] == "Brand Portfolio"

    second = _tick(ingestion, rest, NOW + timedelta(seconds=61))
    third = _tick(ingestion, rest, NOW + timedelta(seconds=122))

    # Search terms keep their own cap of 4 saves a tick; the campaign grain saves its 3 alongside.
    assert (second.reports_saved, third.reports_saved) == (4 + 3, 1)
    assert (third.jobs_completed, second.errors, third.errors) == (1, [], [])
    backfill = _only(rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms"))
    assert (backfill["status"], backfill["rows_written"], backfill["dedupe_key"]) == ("completed", 130, None)
    assert len(rest.tables[DAILY_ROWS]) == 65 * 2
    assert rest.replaced_days[:14] == sorted(rest.replaced_days[:14]) and rest.replaced_days[13] == YESTERDAY
    assert rest.rpc_timeouts["replace_search_term_day"] == 120
    assert all(row["raw_status"] == "kept" and (tmp_path / row["raw_path"]).is_file() for row in _search_term_requests(rest))
    profile = _only(rest.rows(PROFILES))
    assert profile["backfill_done_at"] == (NOW + timedelta(seconds=122)).isoformat()
    assert (profile["data_from"], profile["data_through"], profile["refreshed_on"]) == ("2026-07-11", YESTERDAY,
                                                                                         "2026-09-14")
    assert (profile["cliente"], profile["currency_code"], profile["status"]) == ("cliente-1001", "USD", "active")
    heartbeat = _only(rest.rows(HEARTBEATS))
    assert heartbeat["last_tick_at"] == (NOW + timedelta(seconds=122)).isoformat()
    assert heartbeat["summary"]["jobs_completed"] == 1


def test_duplicate_create_resumes_the_report_amazon_already_has(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    in_flight_id = amazon.add_report("1001", "2026-08-31", YESTERDAY)
    amazon.create_outcomes.append(
        _FakeResponse(425, {"code": "425", "detail": f"The Request is a duplicate of : {in_flight_id}"}))
    ingestion = _ingestion(rest, amazon, tmp_path)

    _tick(ingestion, rest, NOW)

    request = _only(_search_term_requests(rest))
    assert (request["status"], request["amazon_report_id"]) == ("requested", in_flight_id)
    assert amazon.created == []

    summary = _tick(ingestion, rest, NOW + timedelta(seconds=61))

    # The campaign grain saves its three empty chunks and closes its own job alongside.
    assert (summary.reports_saved, summary.jobs_completed, summary.rows_written) == (1 + 3, 1 + 1, 28)
    assert _only(rest.rows(JOBS, trigger="scheduled_daily", job_kind="sp_search_terms"))["status"] == "completed"
    assert _only(rest.rows(PROFILES))["refreshed_on"] == "2026-09-14"


def test_failed_report_retries_after_the_backoff_and_then_completes(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.status_scripts = [["FAILED"], ["COMPLETED"]]
    ingestion = _ingestion(rest, amazon, tmp_path)
    failed_at = NOW + timedelta(seconds=61)

    _tick(ingestion, rest, NOW)
    failure = _tick(ingestion, rest, failed_at)

    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert (job["status"], job["attempts"], job["error_class"]) == ("retrying", 1, "ReportFailed")
    assert job["next_attempt_at"] == (failed_at + timedelta(minutes=5)).isoformat()
    failed_chunk = _only(_search_term_requests(rest))
    assert (failed_chunk["status"], failed_chunk["amazon_status"]) == ("failed", "FAILED")
    assert failure.jobs_failed == 0 and len(failure.errors) == 1

    too_early = _tick(ingestion, rest, failed_at + timedelta(minutes=4))
    assert too_early.reports_created == 0 and _only(_search_term_requests(rest))["status"] == "failed"

    retried = _tick(ingestion, rest, failed_at + timedelta(minutes=5))
    assert retried.reports_created == 1 and len(amazon.created) == 2
    completed = _tick(ingestion, rest, failed_at + timedelta(minutes=6, seconds=1))

    assert completed.jobs_completed == 1
    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert (job["status"], job["attempts"], len(job["attempt_log"])) == ("completed", 1, 1)
    assert _only(_search_term_requests(rest))["status"] == "saved"


def test_chunks_failing_in_the_same_tick_spend_one_attempt_and_all_retry_together(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest)
    amazon.status_scripts = [["FAILED"], ["FAILED"]]
    ingestion = _ingestion(rest, amazon, tmp_path)
    failed_at = NOW + timedelta(seconds=61)

    _tick(ingestion, rest, NOW)
    summary = _tick(ingestion, rest, failed_at)

    backfill = _only(rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms"))
    assert (backfill["status"], backfill["attempts"]) == ("retrying", 1)
    assert [row["status"] for row in _search_term_requests(rest)] == ["failed", "failed", "saved", "saved", "saved"]
    assert len(summary.errors) == 2

    retried = _tick(ingestion, rest, failed_at + timedelta(minutes=5))

    assert retried.reports_created == 2
    assert [row["status"] for row in _search_term_requests(rest)] == ["requested", "requested", "saved", "saved", "saved"]


def test_throttled_report_creation_stops_the_batch_without_spending_attempts(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, "1001", connection_id=5, profile_row=_backfilled())
    _connect_profile(rest, "2002", connection_id=6, profile_row=_backfilled())
    amazon.create_outcomes.append(_FakeResponse(429, {"code": "429", "details": "Too Many Requests"}))
    ingestion = _ingestion(rest, amazon, tmp_path)

    summary = _tick(ingestion, rest, NOW)

    assert (summary.reports_created, amazon.create_attempts, summary.errors) == (0, 1, [])
    # A 429 speaks for the whole app: the campaign grain waits for the next tick too.
    assert amazon.campaign_creates == []
    assert [(row["status"], row["lease_holder"]) for row in _search_term_requests(rest)] == [("to_request", "")] * 2
    assert [job["attempts"] for job in rest.rows(JOBS, job_kind="sp_search_terms")] == [0, 0]

    later = _tick(ingestion, rest, NOW + timedelta(seconds=61))

    # Search terms get their two back first; the campaign grain then creates its slice of three.
    assert later.reports_created == 2 + 3
    assert [job["attempts"] for job in rest.rows(JOBS, job_kind="sp_search_terms")] == [0, 0]


def test_throttled_portfolio_job_waits_five_minutes_without_spending_an_attempt(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    amazon.portfolio_outcome = _FakeResponse(429, {"code": "429"})

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS, job_kind="portfolio_names"))
    assert (job["status"], job["attempts"], job["attempt_log"]) == ("retrying", 0, [])
    assert job["next_attempt_at"] == (NOW + timedelta(minutes=5)).isoformat()


def test_portfolios_without_permission_complete_with_a_warning(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    amazon.portfolio_outcome = _FakeResponse(403, {"code": "403"})

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS, job_kind="portfolio_names"))
    assert (job["status"], job["warning"], job["rows_written"]) == ("completed", NO_PORTFOLIO_ACCESS_WARNING, 0)


def test_needs_reauth_fails_jobs_for_good_and_flags_the_profile(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())

    def dead_token(force_refresh: bool) -> str:
        raise oauth.NeedsReauth("invalid_grant: refresh token revoked")

    summary = _tick(_ingestion(rest, amazon, tmp_path, token_source=dead_token), rest, NOW)

    # A profile that needs re-authorization cannot run any Amazon job, the campaign grain's two included.
    assert summary.jobs_failed == 2 + 2
    assert {job["job_kind"]: (job["status"], job["attempts"], job["error_class"]) for job in rest.rows(JOBS)} == {
        "sp_search_terms": ("failed", 1, "NeedsReauth"),
        # A first load is claimed before the scheduled jobs, so the campaign history meets the dead token itself.
        "sp_campaigns": ("failed", 1, "NeedsReauth"),
        "portfolio_names": ("failed", 1, "NeedsReauth"),
        # Started after the portfolio job hit the dead token: the profile guard fails it before
        # it spends an Amazon call.
        "campaign_entities": ("failed", 1, "ConnectionUnavailable"),
    }
    assert _only(_search_term_requests(rest))["status"] == "failed"
    profile = _only(rest.rows(PROFILES))
    assert profile["status"] == "needs_reauth" and "invalid_grant" in profile["last_error"]
    assert amazon.create_attempts == 0


def test_access_denied_on_reports_fails_the_job_without_retrying(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.create_outcomes.append(_FakeResponse(403, {"code": "403", "details": "Forbidden"}))

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert (job["status"], job["error_class"], job["attempts"]) == ("failed", "AccessDenied", 1)
    assert _only(rest.rows(PROFILES))["last_failure_at"] == NOW.isoformat()


def test_queued_job_past_its_deadline_fails(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    rest.seed(JOBS, integration_slug="amazon_ads", job_kind="sp_search_terms", trigger="scheduled_daily",
              external_account_id="1001", connection_id=5, region="NA", status="retrying", attempts=2,
              window_start="2026-08-31", window_end=YESTERDAY, local_day="2026-09-14",
              next_attempt_at=(NOW - timedelta(hours=1)).isoformat(), deadline_at=(NOW - timedelta(minutes=1)).isoformat(),
              dedupe_key="amazon_ads:1001:day:2026-09-14")

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS))
    assert (job["status"], job["error_class"], job["lease_holder"]) == ("failed", "deadline", "")
    assert summary.jobs_failed == 1
    assert _search_term_requests(rest) == []


def test_manual_refresh_is_requested_before_scheduled_jobs(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, "1001", connection_id=5, profile_row=_backfilled())
    _connect_profile(rest, "2002", connection_id=6, profile_row=_backfilled(refreshed_on="2026-09-14"))
    manual = rest.seed(JOBS, integration_slug="amazon_ads", job_kind="sp_search_terms", trigger="manual",
                       external_account_id="2002", connection_id=6, region="NA", max_attempts=3,
                       window_start="2026-08-31", window_end=YESTERDAY, local_day="2026-09-14",
                       next_attempt_at=NOW.isoformat(), deadline_at=(NOW + timedelta(hours=6)).isoformat(),
                       requested_by="juan")

    summary = _tick(_ingestion(rest, amazon, tmp_path, max_creates_per_tick=1), rest, NOW)

    # The worker's cap is a ceiling for every kind: the campaign grain gets one create too, not its usual three.
    assert summary.reports_created == 1 + 1
    assert amazon.created == [("2002", "2026-08-31", YESTERDAY)]
    assert _only(rest.rows(REQUESTS, job_id=manual["id"]))["status"] == "requested"
    scheduled = _only(rest.rows(JOBS, trigger="scheduled_daily", job_kind="sp_search_terms"))
    assert _only(rest.rows(REQUESTS, job_id=scheduled["id"]))["status"] == "to_request"


def test_empty_day_keeps_the_rows_already_saved_and_warns(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon(rows_per_day=2)
    _connect_profile(rest, profile_row=_backfilled())
    rest.seed(DAILY_ROWS, profile_id="1001", report_date=YESTERDAY, search_term="kept term", clicks=4)
    amazon.empty_days = {YESTERDAY}
    ingestion = _ingestion(rest, amazon, tmp_path)

    _tick(ingestion, rest, NOW)
    summary = _tick(ingestion, rest, NOW + timedelta(seconds=61))

    assert summary.rows_written == 13 * 2
    assert [row["search_term"] for row in rest.rows(DAILY_ROWS, report_date=YESTERDAY)] == ["kept term"]
    assert _only(_search_term_requests(rest))["skipped_days"] == [YESTERDAY]
    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert job["status"] == "completed"
    assert job["warning"].startswith("día vacío") and YESTERDAY in job["warning"]


def test_revoked_connection_marks_the_profile_inactive_and_cancels_its_jobs(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, connection_state="revocado", profile_row=_backfilled(status="active"))
    rest.seed(JOBS, integration_slug="amazon_ads", job_kind="sp_search_terms", trigger="scheduled_daily",
              external_account_id="1001", connection_id=5, status="pending", window_start="2026-08-31",
              window_end=YESTERDAY, local_day="2026-09-14", next_attempt_at=(NOW + timedelta(hours=1)).isoformat(),
              deadline_at=(NOW + timedelta(hours=5)).isoformat())

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    assert _only(rest.rows(PROFILES))["status"] == "inactive"
    job = _only(rest.rows(JOBS))
    assert (job["status"], job["error_message"]) == ("cancelled", PROFILE_INACTIVE_REASON)
    assert (summary.profiles_active, summary.jobs_planned) == (0, 0)


def test_reauthorized_profile_releases_its_failed_backfill_and_plans_a_new_one(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row={"status": "needs_reauth"})
    failed = rest.seed(JOBS, integration_slug="amazon_ads", job_kind="sp_search_terms", trigger="backfill",
                       external_account_id="1001", status="failed", error_class="NeedsReauth",
                       window_start="2026-07-10", window_end="2026-09-12", local_day="2026-09-14",
                       deadline_at=(NOW - timedelta(hours=1)).isoformat(),
                       dedupe_key="amazon_ads:1001:backfill:2026-09-14")

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    assert _only(rest.rows(PROFILES))["status"] == "active"
    assert _only(rest.rows(JOBS, id=failed["id"]))["dedupe_key"] is None
    fresh = _only([job for job in rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms")
                   if job["id"] != failed["id"]])
    assert fresh["dedupe_key"] == "amazon_ads:1001:backfill:2026-09-14" and fresh["window_end"] == YESTERDAY
    assert summary.jobs_planned == 4


def test_missing_tables_give_an_empty_summary_without_touching_amazon(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest)
    rest.missing_tables = set(NEW_TABLES)

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    assert summary == TickSummary()
    assert amazon.create_attempts == 0


def test_raw_reports_are_pruned_at_most_once_per_hour_even_across_restarts(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()

    def expired_raw(name: str):
        raw_file = tmp_path / "1001" / "2026-02" / f"{name}.json.gz"
        raw_file.parent.mkdir(parents=True, exist_ok=True)
        raw_file.write_bytes(b"\x1f\x8b raw")
        rest.seed(REQUESTS, job_id=1, profile_id="1001", window_start="2026-02-01", window_end="2026-02-14",
                  status="saved", raw_status="kept", raw_path=f"1001/2026-02/{name}.json.gz",
                  saved_at=(NOW - timedelta(days=200)).isoformat())
        return raw_file

    first_file = expired_raw("r-first")
    ingestion = _ingestion(rest, amazon, tmp_path)

    assert _tick(ingestion, rest, NOW).raw_pruned == 1
    assert not first_file.exists()
    assert _only(rest.rows(HEARTBEATS))["summary"]["raw_pruned_at"] == NOW.isoformat()

    second_file = expired_raw("r-second")
    assert _tick(ingestion, rest, NOW + timedelta(minutes=10)).raw_pruned == 0
    restarted = _ingestion(rest, amazon, tmp_path)
    assert _tick(restarted, rest, NOW + timedelta(minutes=20)).raw_pruned == 0
    assert second_file.exists()

    assert _tick(restarted, rest, NOW + timedelta(minutes=61)).raw_pruned == 1
    assert not second_file.exists()


def _seed_search_terms_job(rest: _FakePostgrest, **overrides) -> dict:
    job = {
        "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "manual",
        "external_account_id": "1001", "connection_id": 5, "region": "NA", "max_attempts": 3,
        "window_start": "2026-08-31", "window_end": YESTERDAY, "local_day": "2026-09-14",
        "next_attempt_at": (NOW - timedelta(minutes=1)).isoformat(),
        "deadline_at": (NOW + timedelta(hours=5)).isoformat(),
    }
    return rest.seed(JOBS, **{**job, **overrides})


def _claim_as_another_worker(rest: _FakePostgrest, moment: datetime) -> list[dict]:
    rest.now = moment
    return rest.rpc("claim_sync_jobs", {"p_holder": "another-worker", "p_limit": 20, "p_lease_seconds": 900})


def test_saving_a_chunk_renews_the_job_lease_so_nobody_claims_the_job_meanwhile(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest)
    amazon.status_scripts = [["COMPLETED"]] + [["PROCESSING"]] * 4
    ingestion = _ingestion(rest, amazon, tmp_path)
    saved_at = NOW + timedelta(minutes=14)

    _tick(ingestion, rest, NOW)
    summary = _tick(ingestion, rest, saved_at)

    # The campaign grain saves its own three chunks in the same tick.
    assert summary.reports_saved == 1 + 3
    backfill = _only(rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms"))
    assert backfill["status"] == "running"
    assert backfill["lease_expires_at"] == (saved_at + timedelta(seconds=900)).isoformat()
    assert _claim_as_another_worker(rest, NOW + timedelta(minutes=16)) == []


def test_a_job_whose_failure_cannot_be_recorded_does_not_stop_the_batch_and_is_claimed_again_later(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, "1001", connection_id=5, profile_row=_backfilled(refreshed_on="2026-09-14"))
    _connect_profile(rest, "2002", connection_id=6, profile_row=_backfilled(refreshed_on="2026-09-14"))
    stranded = _seed_search_terms_job(rest, next_attempt_at=(NOW - timedelta(minutes=2)).isoformat())
    other = _seed_search_terms_job(rest, external_account_id="2002", connection_id=6)
    rest.fail_once("select", REQUESTS, lambda params: params.get("job_id") == f"eq.{stranded['id']}")
    rest.fail_once("update", JOBS, lambda call: call["params"].get("id") == f"eq.{stranded['id']}")
    ingestion = _ingestion(rest, amazon, tmp_path)

    summary = _tick(ingestion, rest, NOW)

    assert any(error.startswith(f"job {stranded['id']}: ConnectionError") for error in summary.errors)
    assert (_only(rest.rows(JOBS, id=stranded["id"]))["status"], rest.rows(REQUESTS, job_id=stranded["id"])) == (
        "running", [])
    assert _only(rest.rows(REQUESTS, job_id=other["id"]))["status"] == "requested"

    lease_lapsed = NOW + timedelta(minutes=16)
    _tick(ingestion, rest, lease_lapsed)
    _tick(ingestion, rest, lease_lapsed + timedelta(seconds=61))

    assert [_only(rest.rows(JOBS, id=job["id"]))["status"] for job in (stranded, other)] == ["completed", "completed"]
    assert _only(rest.rows(JOBS, id=stranded["id"]))["attempts"] == 0


def test_a_failed_chunk_whose_write_is_lost_still_sends_its_job_to_retry(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.status_scripts = [["FAILED"]]
    ingestion = _ingestion(rest, amazon, tmp_path)
    _tick(ingestion, rest, NOW)
    rest.fail_once("update", REQUESTS, lambda call: call["changes"].get("status") == "failed")

    _tick(ingestion, rest, NOW + timedelta(seconds=61))

    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert (job["status"], job["attempts"], job["error_class"]) == ("retrying", 1, "ReportFailed")
    assert _only(_search_term_requests(rest))["status"] == "requested"


def test_a_report_amazon_failed_keeps_amazons_reason_when_the_gateway_blips(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.status_scripts = [["FAILED"]]
    ingestion = _ingestion(rest, amazon, tmp_path)
    _tick(ingestion, rest, NOW)
    rest.fail_once("update", REQUESTS, lambda call: call["changes"].get("status") != "failed")

    _tick(ingestion, rest, NOW + timedelta(seconds=61))

    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    chunk = _only(_search_term_requests(rest))
    assert (job["status"], job["error_class"]) == ("retrying", "ReportFailed")
    assert (chunk["status"], chunk["error_class"], chunk["amazon_status"]) == ("failed", "ReportFailed", "FAILED")


def test_a_running_job_left_with_saved_and_failed_chunks_only_goes_to_retry(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    job = _seed_search_terms_job(rest, status="running", phase="waiting", lease_holder="worker-test",
                                 window_start="2026-08-17", lease_expires_at=(NOW + timedelta(minutes=10)).isoformat())
    rest.seed(REQUESTS, job_id=job["id"], profile_id="1001", window_start="2026-08-31", window_end=YESTERDAY,
              status="saved", row_count=28, saved_at=(NOW - timedelta(minutes=5)).isoformat())
    rest.seed(REQUESTS, job_id=job["id"], profile_id="1001", window_start="2026-08-17", window_end="2026-08-30",
              status="failed", error_class="ReportFailed", error_message="Amazon could not build report")

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    stranded = _only(rest.rows(JOBS, id=job["id"]))
    assert (stranded["status"], stranded["attempts"], stranded["error_class"]) == ("retrying", 1, "ReportFailed")
    assert stranded["error_message"] == "Amazon could not build report"
    assert summary.jobs_failed == 0


def test_a_failed_job_write_after_a_save_keeps_the_chunk_saved(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    ingestion = _ingestion(rest, amazon, tmp_path)
    _tick(ingestion, rest, NOW)
    rest.fail_once("update", JOBS, lambda call: call["changes"].get("phase") == "waiting")

    summary = _tick(ingestion, rest, NOW + timedelta(seconds=61))

    request = _only(_search_term_requests(rest))
    assert request["status"] == "saved" and (tmp_path / request["raw_path"]).is_file()
    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert (job["status"], job["attempts"]) == ("completed", 0)
    assert any("ConnectionError" in error for error in summary.errors)


def test_a_stop_request_ends_the_tick_between_report_requests_and_frees_the_rest(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest)
    ingestion = _ingestion(rest, amazon, tmp_path)

    summary = ingestion.run_tick(NOW, stop_requested=lambda: len(amazon.created) >= 2)

    assert (len(amazon.created), summary.reports_created) == (2, 2)
    waiting = _search_term_requests(rest, status="to_request")
    assert len(waiting) == 3 and all(request["lease_holder"] == "" for request in waiting)
    assert _only(rest.rows(HEARTBEATS))["summary"]["reports_created"] == 2


def test_heartbeat_records_when_it_was_written_not_when_the_tick_started(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    written_at = NOW + timedelta(minutes=4)

    _tick(_ingestion(rest, amazon, tmp_path, clock=lambda: written_at), rest, NOW)

    assert _only(rest.rows(HEARTBEATS))["last_tick_at"] == written_at.isoformat()


def test_a_save_cut_off_twice_fails_the_chunk_instead_of_being_tried_again(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    ingestion = _ingestion(rest, amazon, tmp_path)
    _tick(ingestion, rest, NOW)

    for moment in (NOW + timedelta(seconds=61), NOW + timedelta(minutes=17)):
        rest.fail_once("rpc", "replace_search_term_day", error=_WorkerKilled("out of memory"))
        with pytest.raises(_WorkerKilled):
            _tick(ingestion, rest, moment)
    assert (_only(_search_term_requests(rest))["status"], _only(_search_term_requests(rest))["save_attempts"]) == ("saving", 2)

    _tick(ingestion, rest, NOW + timedelta(minutes=33))

    request = _only(_search_term_requests(rest))
    assert (request["status"], request["error_class"], request["error_message"]) == (
        "failed", "SaveCrashed", SAVE_CRASHED_MESSAGE)
    job = _only(rest.rows(JOBS, job_kind="sp_search_terms"))
    assert (job["status"], job["error_class"]) == ("failed", "SaveCrashed")
    assert rest.rows(DAILY_ROWS) == []


def test_retrying_a_failed_chunk_resets_its_save_count_and_removes_its_old_raw_file(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    job = _seed_search_terms_job(rest, status="retrying", attempts=1)
    old_raw = tmp_path / "1001" / "2026-09" / "old-report.json.gz"
    old_raw.parent.mkdir(parents=True)
    old_raw.write_bytes(b"\x1f\x8b old")
    rest.seed(REQUESTS, job_id=job["id"], profile_id="1001", window_start="2026-08-31", window_end=YESTERDAY,
              status="failed", save_attempts=2, raw_status="kept", raw_path="1001/2026-09/old-report.json.gz",
              raw_bytes=10, raw_sha256="ab" * 32, error_class="SaveCrashed")

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    request = _only(_search_term_requests(rest))
    assert request["status"] == "requested"
    assert (request["save_attempts"], request["raw_status"], request["raw_path"], request["raw_bytes"],
            request["raw_sha256"]) == (0, "none", "", None, "")
    assert not old_raw.exists()


def test_a_profile_above_twelve_thousand_rows_a_day_gets_seven_day_chunks(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    rest.seed(REQUESTS, job_id=99, profile_id="1001", window_start="2026-08-30", window_end="2026-09-12",
              status="saved", row_count=12_001 * 14, saved_at=(NOW - timedelta(days=1)).isoformat())

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    daily = _only(rest.rows(JOBS, trigger="scheduled_daily", job_kind="sp_search_terms"))
    windows = [(request["window_start"], request["window_end"]) for request in rest.rows(REQUESTS, job_id=daily["id"])]
    assert windows == [("2026-09-07", YESTERDAY), ("2026-08-31", "2026-09-06")]


def test_a_cancelled_backfill_is_planned_again_the_next_local_day_but_not_the_same_day(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest)
    amazon.status_scripts = [["PROCESSING"]] * 5
    ingestion = _ingestion(rest, amazon, tmp_path)
    _tick(ingestion, rest, NOW)
    first = _only(rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms"))
    rest.update(JOBS, {"id": f"eq.{first['id']}"},
                {"status": "cancelled", "lease_holder": "", "lease_expires_at": None})

    same_day = _tick(ingestion, rest, NOW + timedelta(hours=2))
    assert (same_day.jobs_planned, len(rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms"))) == (0, 1)

    _tick(ingestion, rest, NOW + timedelta(days=1))

    fresh = _only([job for job in rest.rows(JOBS, trigger="backfill", job_kind="sp_search_terms")
                   if job["id"] != first["id"]])
    assert (fresh["dedupe_key"], fresh["window_end"]) == ("amazon_ads:1001:backfill:2026-09-15", "2026-09-14")


def test_reauthorized_profile_gets_todays_refresh_again_after_its_day_jobs_failed(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(status="needs_reauth"))
    failed_day = _seed_search_terms_job(rest, trigger="scheduled_daily", status="failed", error_class="NeedsReauth",
                                        dedupe_key="amazon_ads:1001:day:2026-09-14")
    rest.seed(JOBS, integration_slug="amazon_ads", job_kind="portfolio_names", trigger="scheduled_daily",
              external_account_id="1001", connection_id=5, region="NA", status="failed", error_class="NeedsReauth",
              local_day="2026-09-14", deadline_at=(NOW + timedelta(hours=5)).isoformat(),
              dedupe_key="amazon_ads:1001:portfolios:2026-09-14")

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    assert summary.jobs_planned == 4
    assert _only(rest.rows(JOBS, id=failed_day["id"]))["dedupe_key"] is None
    fresh_day = _only([job for job in rest.rows(JOBS, trigger="scheduled_daily", job_kind="sp_search_terms")
                       if job["id"] != failed_day["id"]])
    assert fresh_day["dedupe_key"] == "amazon_ads:1001:day:2026-09-14"


def test_todays_closed_scheduled_jobs_block_planning_only_while_they_hold_their_key():
    profile = {"profile_id": "1001", "status": "active", "timezone": "America/Los_Angeles", "region": "NA",
               "backfill_done_at": "2026-08-01T00:00:00+00:00"}
    failed_day = {"id": 1, "job_kind": "sp_search_terms", "trigger": "scheduled_daily", "status": "failed",
                  "local_day": "2026-09-14", "window_start": "2026-08-31", "window_end": YESTERDAY}
    failed_portfolios = {"id": 2, "job_kind": "portfolio_names", "trigger": "scheduled_daily", "status": "failed",
                         "local_day": "2026-09-14"}

    holding = _profile_state(profile, [{**failed_day, "dedupe_key": "amazon_ads:1001:day:2026-09-14"},
                                       {**failed_portfolios, "dedupe_key": "amazon_ads:1001:portfolios:2026-09-14"}],
                             NOW)
    released = _profile_state(profile, [{**failed_day, "dedupe_key": None}, {**failed_portfolios, "dedupe_key": None}],
                              NOW)

    assert (holding.has_open_day_job_today, holding.has_portfolio_job_today) == (True, True)
    assert (released.has_open_day_job_today, released.has_portfolio_job_today) == (False, False)


def test_a_claimed_job_of_a_disconnected_profile_fails_without_calling_amazon(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, connection_state="revocado", profile_row=_backfilled(status="inactive"))
    retry = _seed_search_terms_job(rest, trigger="retry", max_attempts=8)

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS, id=retry["id"]))
    assert (job["status"], job["error_class"], job["attempts"]) == ("failed", "ConnectionUnavailable", 1)
    assert _search_term_requests(rest) == [] and amazon.create_attempts == 0


def test_cached_tokens_of_connections_that_are_not_active_are_forgotten(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, "1001", connection_id=5, connection_state="revocado", profile_row=_backfilled())
    _connect_profile(rest, "2002", connection_id=6, profile_row=_backfilled(refreshed_on="2026-09-14"))
    tokens = _FakeTokens()

    _tick(_ingestion(rest, amazon, tmp_path, tokens=tokens), rest, NOW)

    assert tokens.forgotten == [5]


def test_amazon_calls_carry_the_client_id_of_the_latest_token_refresh(tmp_path, monkeypatch):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    tokens = _RotatingCredentialTokens(["client-before-swap", "client-after-swap"])
    monkeypatch.setattr(ingestion_module, "AdsApiClient",
                        functools.partial(AdsApiClient, session=amazon, sleep=lambda seconds: None, max_retries=0))
    ingestion = IngestionJob(rest=rest, jobs=SyncJobStore(rest), tokens=tokens, raw_dir=tmp_path, holder="worker-test",
                             download_session=amazon, clock=lambda: rest.now)

    _tick(ingestion, rest, NOW)

    # The campaign grain's entity listing and its three report creates carry the latest id too.
    assert amazon.client_ids == ["client-before-swap", "client-after-swap"] + ["client-after-swap"] * 4


def test_a_failed_profile_read_only_writes_the_heartbeat(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(data_from="2026-07-01"))
    rest.fail_once("select", PROFILES, lambda params: params.get("select") == "*")

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    assert (summary.jobs_planned, summary.reports_created, rest.rows(JOBS), amazon.create_attempts) == (0, 0, [], 0)
    assert _only(rest.rows(PROFILES))["data_from"] == "2026-07-01"
    assert _only(rest.rows(HEARTBEATS))["summary"]["errors"][0].startswith("read_profiles: ConnectionError")


def test_retention_is_judged_when_a_chunk_is_created_not_when_it_was_planned(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    backfill = _seed_search_terms_job(rest, trigger="backfill", status="retrying", attempts=1, max_attempts=6,
                                      window_start="2026-07-02", window_end="2026-09-04", local_day="2026-09-05",
                                      dedupe_key="amazon_ads:1001:backfill:2026-09-05")
    past = rest.seed(REQUESTS, job_id=backfill["id"], profile_id="1001", window_start="2026-07-02",
                     window_end="2026-07-08", status="failed", error_class="AdsApiError")
    trimmed = rest.seed(REQUESTS, job_id=backfill["id"], profile_id="1001", window_start="2026-07-09",
                        window_end="2026-07-22", status="failed", error_class="AdsApiError")

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    assert amazon.created == [("1001", "2026-07-11", "2026-07-22")]
    past, trimmed = _only(rest.rows(REQUESTS, id=past["id"])), _only(rest.rows(REQUESTS, id=trimmed["id"]))
    assert (past["status"], past["row_count"], past["skipped_days"]) == (
        "saved", 0, [f"2026-07-0{day}" for day in range(2, 9)])
    assert (trimmed["status"], trimmed["window_start"]) == ("requested", "2026-07-11")


class _DaysNotKept(_FakePostgrest):
    """Serializes each day like the real RPC call but keeps nothing, so only the save path's memory is measured."""

    def _replace_search_term_day(self, p_profile_id, p_day, p_rows):
        json.dumps(p_rows)
        return len(p_rows)


def test_saving_a_report_peaks_below_what_parsing_the_whole_file_takes(tmp_path):
    report_path, rows_per_day = tmp_path / "report.json.gz", 1000
    amazon = _FakeAmazon(rows_per_day=rows_per_day)
    two_weeks = amazon._report_rows({"start": "2026-08-01", "end": "2026-08-14"})
    with gzip.open(report_path, "wt", encoding="utf-8") as report_file:
        json.dump([{**api_row, "keywordId": 300000 + position, "searchTerm": f"a shopper search term {position}"}
                   for position, api_row in enumerate(two_weeks)], report_file)
    del two_weeks
    tracemalloc.start()
    with gzip.open(report_path, "rt", encoding="utf-8") as report_file:
        parsed_report = json.load(report_file)
    parsed_bytes = tracemalloc.get_traced_memory()[1]
    del parsed_report
    tracemalloc.stop()
    rest = _DaysNotKept(NOW)
    ingestion = _ingestion(rest, amazon, tmp_path)
    tick = _Tick(now=NOW, summary=TickSummary(), profiles={"1001": {"currency_code": "USD"}})

    tracemalloc.start()
    rows_written, empty_days = ingestion._replace_days(
        tick, {"profile_id": "1001", "window_start": "2026-08-01", "window_end": "2026-08-14"}, report_path)
    peak_bytes = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    assert (rows_written, empty_days) == (14 * rows_per_day, [])
    # Measured: about 0.65x for the day-by-day save of compact rows, 1.05x for parsing and normalizing it all at once.
    assert peak_bytes < parsed_bytes * 0.85, (peak_bytes, parsed_bytes)


def test_a_retried_job_uses_the_authorization_its_profile_has_now(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, "1001", connection_id=6, profile_row=_backfilled(refreshed_on="2026-09-14", connection_id=6))
    rest.seed("integration_connections", id=5, integration_slug="amazon_ads", estado="needs_reauth")
    failed = _seed_search_terms_job(rest, status="failed", error_class="NeedsReauth", connection_id=5)
    ingestion = _ingestion(rest, amazon, tmp_path)
    retry_id = SyncJobStore(rest).retry(failed["id"], "admin")

    _tick(ingestion, rest, NOW)
    _tick(ingestion, rest, NOW + timedelta(seconds=61))

    retry = _only(rest.rows(JOBS, id=retry_id))
    assert (retry["status"], retry["connection_id"], retry["retry_of"]) == ("completed", 6, failed["id"])
    assert set(amazon.connections_used) == {("NA", 6)}
    rest.tables[PROFILES][0]["status"] = "inactive"
    assert SyncJobStore(rest).retry(failed["id"], "admin") is None


def test_the_campaign_grain_writes_its_own_table_and_never_moves_the_search_term_freshness(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon(campaign_rows_per_day=2)
    freshness = {"data_from": "2026-07-11", "data_through": YESTERDAY,
                 "last_success_at": "2026-09-14T10:00:00+00:00"}
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14", **freshness))
    ingestion = _ingestion(rest, amazon, tmp_path)

    _tick(ingestion, rest, NOW)
    _tick(ingestion, rest, NOW + timedelta(seconds=61))

    campaign_rows = rest.tables[CAMPAIGN_DAILY]
    days = {row["report_date"] for row in campaign_rows}
    assert {row["campaign_id"] for row in campaign_rows} == {"900", "901"}
    assert len(campaign_rows) == 2 * len(days) and max(days) == YESTERDAY
    assert rest.tables[DAILY_ROWS] == []
    campaign_job = _only(rest.rows(JOBS, job_kind=CAMPAIGNS_KIND))
    assert (campaign_job["status"], campaign_job["rows_written"]) == ("completed", len(campaign_rows))
    # ads_profile_sync describes search-term coverage; the STR picker reads its freshness from there.
    profile = _only(rest.rows(PROFILES))
    assert {column: profile[column] for column in freshness} == freshness
    assert profile["refreshed_on"] == "2026-09-14"


def _seed_campaign_job(rest: _FakePostgrest, *, window_start: str, window_end: str, local_day: str) -> dict:
    return rest.seed(JOBS, integration_slug="amazon_ads", job_kind=CAMPAIGNS_KIND, trigger="scheduled_daily",
                     external_account_id="1001", status="completed", window_start=window_start,
                     window_end=window_end, local_day=local_day, deadline_at=(NOW - timedelta(hours=12)).isoformat(),
                     dedupe_key=f"amazon_ads:1001:campaigns:{local_day}")


def test_a_profile_whose_nights_asked_sixty_five_days_keeps_its_history_and_asks_the_last_week(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    _seed_campaign_job(rest, window_start="2026-07-10", window_end="2026-09-12", local_day="2026-09-13")

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    today = _only(rest.rows(JOBS, job_kind=CAMPAIGNS_KIND, local_day="2026-09-14"))
    assert (today["trigger"], today["window_start"], today["window_end"]) == ("scheduled_daily", "2026-09-07",
                                                                              YESTERDAY)


def test_the_campaign_history_loads_once_and_the_next_day_asks_only_the_last_week(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon(campaign_rows_per_day=1)
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    ingestion = _ingestion(rest, amazon, tmp_path)

    _tick(ingestion, rest, NOW)
    _tick(ingestion, rest, NOW + timedelta(seconds=61))
    same_day = _tick(ingestion, rest, NOW + timedelta(hours=2))

    history = _only(rest.rows(JOBS, job_kind=CAMPAIGNS_KIND))
    assert (history["trigger"], history["status"], history["window_start"]) == ("backfill", "completed", "2026-07-11")
    # Its dedupe key is released on completion; it still counts as today's job.
    assert same_day.jobs_planned == 0

    _tick(ingestion, rest, NOW + timedelta(days=1))

    next_day = _only(rest.rows(JOBS, job_kind=CAMPAIGNS_KIND, local_day="2026-09-15"))
    assert (next_day["trigger"], next_day["window_start"], next_day["window_end"]) == (
        "scheduled_daily", "2026-09-08", "2026-09-14")


def test_a_profile_without_a_history_or_a_sunday_pass_in_two_weeks_loads_the_history_again(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled(refreshed_on="2026-09-14"))
    _seed_campaign_job(rest, window_start="2026-06-20", window_end="2026-08-23", local_day="2026-08-24")

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    today = _only(rest.rows(JOBS, job_kind=CAMPAIGNS_KIND, local_day="2026-09-14"))
    assert (today["trigger"], today["window_start"], today["window_end"]) == ("backfill", "2026-07-11", YESTERDAY)


def test_a_campaign_history_open_since_yesterday_blocks_another_one():
    row = {"profile_id": "1001", "timezone": "America/Los_Angeles", "region": "NA", "status": "active"}
    jobs = [{"id": 1, "job_kind": CAMPAIGNS_KIND, "trigger": "backfill", "status": "running",
             "local_day": "2026-09-13", "dedupe_key": "amazon_ads:1001:campaigns-history:2026-09-13"}]

    state = _profile_state(row, jobs, NOW)

    assert (state.has_open_campaign_job, state.has_campaign_job_today, state.campaign_history_done) == (
        True, False, False)
    assert CAMPAIGNS_KIND not in [job.job_kind for job in ingestion_module.plan_jobs(state, NOW)]


def test_campaign_entities_are_saved_as_the_profile_campaign_universe(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())

    _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    campaign = _only(rest.rows(CAMPAIGNS))
    assert {key: campaign[key] for key in ("profile_id", "campaign_id", "name", "state", "budget_amount",
                                            "bidding_strategy", "portfolio_id", "start_date")} == {
        "profile_id": "1001", "campaign_id": "909", "name": "Demo - SP - KW - EXACT", "state": "ENABLED",
        "budget_amount": 15.0, "bidding_strategy": "MANUAL", "portfolio_id": "444", "start_date": "2026-03-21",
    }
    assert _only(rest.rows(JOBS, job_kind=CAMPAIGN_ENTITIES_KIND))["status"] == "completed"


def test_a_profile_that_may_not_list_campaigns_completes_the_job_with_a_warning(tmp_path):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.campaign_outcome = _FakeResponse(403, {"code": "403", "details": "Forbidden"})

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS, job_kind=CAMPAIGN_ENTITIES_KIND))
    assert (job["status"], job["warning"]) == ("completed", NO_CAMPAIGN_ACCESS_WARNING)
    assert rest.rows(CAMPAIGNS) == [] and summary.errors == []


# ── Targeting of SP, SB and SD, and SB / SD campaigns ───────────────────────────


def _sd_campaign(campaign_id: int = 501) -> dict:
    return {"campaignId": campaign_id, "portfolioId": 444, "name": "Demo - SD - Products", "tactic": "T00020",
            "startDate": "20260110", "state": "enabled", "costType": "cpc", "budget": 15.0, "budgetType": "daily"}


def _sd_campaign_row(day: str, campaign_id: int = 501, **overrides) -> dict:
    row = {"date": day, "campaignId": campaign_id, "impressions": 900, "impressionsViews": 0, "clicks": 9,
           "cost": 4.5, "purchases": 2, "sales": 40.0, "purchasesClicks": 1, "salesClicks": 20.0, "costType": "CPC",
           "campaignBudgetAmount": 15.0, "campaignBudgetCurrencyCode": "USD"}
    row.update(overrides)
    return row


def test_the_sp_target_list_is_saved_as_the_sp_target_universe(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sp_keywords = [{"keywordId": "7001", "campaignId": "909", "adGroupId": "8001", "keywordText": "demo kw",
                           "matchType": "EXACT", "state": "ENABLED", "bid": 0.9}]
    amazon.sp_targets = [{"targetId": "7002", "campaignId": "909", "adGroupId": "8002", "expressionType": "AUTO",
                          "expression": [{"type": "QUERY_BROAD_REL_MATCHES"}], "state": "ENABLED", "bid": 0.4}]

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    targets = {row["target_id"]: row for row in rest.rows(TARGETS)}
    assert set(targets) == {"7001", "7002"}
    assert {row["ad_product"] for row in targets.values()} == {"SP"}
    assert (targets["7001"]["target_kind"], targets["7002"]["target_kind"]) == ("keyword", "auto")
    job = _only(rest.rows(JOBS, job_kind=SP_TARGETS_KIND))
    assert (job["status"], job["rows_written"]) == ("completed", 2) and summary.errors == []


def test_the_sp_product_ads_list_saves_the_asin_each_ad_group_advertises(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sp_product_ads = [{"adId": "9001", "campaignId": "909", "adGroupId": "8001", "asin": "B0DEMO0001",
                              "sku": "DEMO-1", "state": "ENABLED"},
                             {"adId": "9002", "campaignId": "909", "adGroupId": "8001", "asin": "B0DEMO0002",
                              "sku": "DEMO-2", "state": "PAUSED"}]

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    saved = {row["ad_id"]: row for row in rest.rows("ads_product_ad")}
    assert set(saved) == {"9001", "9002"}
    assert {(row["ad_group_id"], row["asin"]) for row in saved.values()} == {("8001", "B0DEMO0001"),
                                                                            ("8001", "B0DEMO0002")}
    job = _only(rest.rows(JOBS, job_kind=SP_PRODUCT_ADS_KIND))
    assert (job["status"], job["rows_written"]) == ("completed", 2) and summary.errors == []


def test_sb_and_sd_reports_are_only_planned_once_their_list_found_campaigns(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sd_campaigns = [_sd_campaign()]
    ingestion = _ingestion(rest, amazon, tmp_path)

    _tick(ingestion, rest, NOW)
    _tick(ingestion, rest, NOW + timedelta(seconds=61))

    planned = {row["job_kind"] for row in rest.tables[JOBS]}
    assert {SD_CAMPAIGNS_KIND, SP_TARGETING_KIND} <= planned
    # No SB campaign in the account: its list closes with none, and no SB report is ever asked for.
    assert _only(rest.rows(JOBS, job_kind=SB_ENTITIES_KIND))["rows_written"] == 0
    assert not {SB_CAMPAIGNS_KIND, SB_TARGETING_KIND} & planned
    assert _only(rest.rows(PRODUCT_CAMPAIGNS))["campaign_id"] == "501"


def test_an_account_without_sponsored_brands_closes_its_list_with_a_warning_not_a_failure(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sb_outcome = _FakeResponse(403, {"code": "403", "details": "Forbidden"})

    summary = _tick(_ingestion(rest, amazon, tmp_path), rest, NOW)

    job = _only(rest.rows(JOBS, job_kind=SB_ENTITIES_KIND))
    assert (job["status"], job["rows_written"], job["warning"]) == ("completed", 0, NO_SB_ACCESS_WARNING)
    assert summary.errors == []


def test_an_sd_report_writes_its_own_product_day_and_never_the_sp_campaign_table(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sd_campaigns = [_sd_campaign()]
    amazon.product_report_rows["sdCampaigns"] = [_sd_campaign_row(YESTERDAY), _sd_campaign_row("2026-09-12")]
    ingestion = _ingestion(rest, amazon, tmp_path)

    for seconds in (0, 61, 122, 183):
        _tick(ingestion, rest, NOW + timedelta(seconds=seconds))

    rows = rest.tables[PRODUCT_CAMPAIGN_DAILY]
    assert {(row["ad_product"], row["report_date"]) for row in rows} == {("SD", YESTERDAY), ("SD", "2026-09-12")}
    assert {(row["sales"], row["sales_clicks"]) for row in rows} == {(40.0, 20.0)}
    assert rest.tables[CAMPAIGN_DAILY] == []
    job = _only(rest.rows(JOBS, job_kind=SD_CAMPAIGNS_KIND))
    assert (job["status"], job["trigger"], job["rows_written"]) == ("completed", "backfill", 2)
    history = [create for create in amazon.product_creates if create[0] == "sdCampaigns"]
    assert min(start for _, _, start, _ in history) == "2026-07-11"


def _sb_campaign(campaign_id: str, *, old_format: bool) -> dict:
    return {"campaignId": campaign_id, "name": f"Demo SBH {campaign_id}", "state": "ENABLED", "budget": 10.0,
            "budgetType": "DAILY", "costType": "CPC", "isMultiAdGroupsEnabled": not old_format,
            "bidding": {"bidOptimization": False}}


def _sb_v3_row(day: str, campaign_id: int) -> dict:
    return {"date": day, "campaignId": campaign_id, "impressions": 500, "clicks": 5, "cost": 7.0, "purchases": 1,
            "sales": 25.0, "purchasesClicks": 1, "salesClicks": 25.0, "costType": "CPC", "viewableImpressions": 0,
            "campaignBudgetAmount": 10.0, "campaignBudgetCurrencyCode": "USD", "topOfSearchImpressionShare": 12.5,
            "newToBrandPurchases": 0, "newToBrandSales": 0}


def _v2_row(campaign_id: int, **overrides) -> dict:
    row = {"campaignId": campaign_id, "impressions": 900, "clicks": 12, "cost": 30.5, "attributedConversions14d": 3,
           "attributedSales14d": 99.0, "attributedOrdersNewToBrand14d": 1, "attributedSalesNewToBrand14d": 33.0}
    row.update(overrides)
    return row


def _tick_until_closed(ingestion: IngestionJob, rest: _FakePostgrest, kinds: tuple[str, ...],
                       max_ticks: int = 60) -> None:
    # A v2 history is 60 one-day reports at 6 in flight: about 20 ticks.
    for position in range(max_ticks):
        _tick(ingestion, rest, NOW + timedelta(seconds=61 * position))
        jobs = [job for kind in kinds for job in rest.rows(JOBS, job_kind=kind)]
        if len(jobs) == len(kinds) and all(job["status"] not in OPEN_STATUSES for job in jobs):
            return
    raise AssertionError(f"{kinds} still open after {max_ticks} ticks")


def test_old_format_sb_campaigns_load_from_the_v2_report_a_day_at_a_time(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sb_campaigns = [_sb_campaign("601", old_format=True), _sb_campaign("602", old_format=False)]
    # v2 also brings the new-format campaign, which v3 reports: it must not be stored twice.
    amazon.v2_rows_by_day[YESTERDAY] = [_v2_row(601), _v2_row(602, cost=7.0)]
    amazon.product_report_rows["sbCampaigns"] = [_sb_v3_row(YESTERDAY, 602)]
    ingestion = _ingestion(rest, amazon, tmp_path)

    _tick_until_closed(ingestion, rest, (SB_LEGACY_KIND, SB_CAMPAIGNS_KIND))

    job = _only(rest.rows(JOBS, job_kind=SB_LEGACY_KIND))
    assert (job["status"], job["trigger"]) == ("completed", "backfill")
    days = sorted(day for _, day, _ in amazon.v2_creates)
    assert (days[0], days[-1], len(days)) == ("2026-07-16", YESTERDAY, 60)
    assert {body["creativeType"] for *_, body in amazon.v2_creates} == {"all"}
    by_campaign = {row["campaign_id"]: row for row in rest.tables[PRODUCT_CAMPAIGN_DAILY]}
    # Each source rewrote only its own rows of the day: v2 kept v3's campaign, and v3 kept v2's.
    assert {campaign_id: row["source"] for campaign_id, row in by_campaign.items()} == {"601": "v2", "602": "v3"}
    legacy = by_campaign["601"]
    assert (legacy["cost"], legacy["purchases"], legacy["purchases_clicks"], legacy["sales"], legacy["sales_clicks"],
            legacy["new_to_brand_sales"]) == (30.5, 3, 3, 99.0, 99.0, 33.0)
    assert by_campaign["602"]["cost"] == 7.0


def test_an_account_without_old_format_sb_campaigns_never_asks_the_v2_report(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    amazon.sb_campaigns = [_sb_campaign("602", old_format=False)]
    ingestion = _ingestion(rest, amazon, tmp_path)

    for seconds in (0, 61, 122):
        _tick(ingestion, rest, NOW + timedelta(seconds=seconds))

    assert SB_CAMPAIGNS_KIND in {row["job_kind"] for row in rest.tables[JOBS]}
    assert rest.rows(JOBS, job_kind=SB_LEGACY_KIND) == [] and amazon.v2_creates == []


def test_a_completed_history_turns_the_next_days_into_fourteen_day_refreshes(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    ingestion = _ingestion(rest, amazon, tmp_path)
    for seconds in (0, 61, 122):
        _tick(ingestion, rest, NOW + timedelta(seconds=seconds))
    assert _only(rest.rows(JOBS, job_kind=SP_TARGETING_KIND))["status"] == "completed"

    next_day = NOW + timedelta(days=1)
    _tick(ingestion, rest, next_day)

    daily = _only(rest.rows(JOBS, job_kind=SP_TARGETING_KIND, local_day="2026-09-15"))
    assert (daily["trigger"], daily["window_start"], daily["window_end"]) == (
        "scheduled_daily", "2026-09-01", "2026-09-14")


def test_the_same_day_a_history_finishes_no_second_refresh_is_planned(tmp_path, with_products):
    rest, amazon = _FakePostgrest(NOW), _FakeAmazon()
    _connect_profile(rest, profile_row=_backfilled())
    ingestion = _ingestion(rest, amazon, tmp_path)

    for seconds in (0, 61, 122, 183, 244):
        _tick(ingestion, rest, NOW + timedelta(seconds=seconds))

    assert len(rest.rows(JOBS, job_kind=SP_TARGETING_KIND)) == 1


def test_profile_state_reads_the_new_kinds_from_the_job_queue():
    row = {"profile_id": "1001", "timezone": "America/Los_Angeles", "region": "NA", "status": "active"}
    jobs = [
        {"id": 1, "job_kind": SP_TARGETS_KIND, "status": "completed", "local_day": "2026-09-14", "dedupe_key": None,
         "rows_written": 12},
        {"id": 2, "job_kind": SD_ENTITIES_KIND, "status": "completed", "local_day": "2026-09-14",
         "dedupe_key": "k", "rows_written": 3},
        {"id": 3, "job_kind": SP_TARGETING_KIND, "status": "running", "local_day": "2026-09-13", "dedupe_key": "k"},
        {"id": 4, "job_kind": SB_ENTITIES_KIND, "status": "failed", "local_day": "2026-09-14", "dedupe_key": None,
         "rows_written": None},
    ]

    state = _profile_state(row, jobs, NOW, frozenset({SD_CAMPAIGNS_KIND}))

    assert state.product_kinds_today == {SP_TARGETS_KIND, SD_ENTITIES_KIND}
    assert state.product_kinds_open == {SP_TARGETING_KIND}
    assert state.entity_rows_today == {SP_TARGETS_KIND: 12, SD_ENTITIES_KIND: 3}
    assert state.product_histories_done == {SD_CAMPAIGNS_KIND}

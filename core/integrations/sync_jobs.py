"""The provider-agnostic queue of sync jobs, over `integration_sync_jobs`.

The worker enqueues, claims and closes jobs; the app lists them and asks for a
manual refresh, a retry or a cancel through the migration's functions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone

from core.integrations.store import StoreError, _error_message, _Rest

log = logging.getLogger(__name__)

JOBS_TABLE = "integration_sync_jobs"

JOB_STATUSES = ("pending", "running", "retrying", "completed", "failed", "cancelled")
OPEN_STATUSES = ("pending", "running", "retrying")
PHASES = ("", "requesting", "waiting", "saving")
RETRY_DELAYS_MIN = (5, 15, 30, 60, 120)

# One-off jobs: once done, the same dedupe key must be free to be enqueued again.
_RELEASES_DEDUPE_ON_COMPLETE = ("backfill", "manual", "retry")
_PROBLEM_FILTER = "(status.in.(failed,retrying),attempts.gt.0,warning.neq.\"\")"
_MESSAGE_MAX_CHARS = 500
_DEADLINE_MESSAGE = "Venció el plazo antes de completarse."
# Amazon can take up to 3 h to build a report the job already asked for; failing it sooner would waste it.
RUNNING_DEADLINE_GRACE = timedelta(minutes=210)

_URL_QUERY = re.compile(r"(https?://[^\s?#'\"<>]+)\?[^\s'\"<>]*")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=|-]+")
_LWA_TOKEN = re.compile(r"Atz[ar]\|[^\s'\",]+")
_SECRET_PARAM = re.compile(r"(?i)\b(access_token|refresh_token|client_secret)=[^\s&'\",]+")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")


@dataclass(frozen=True)
class SyncJob:
    id: int
    integration_slug: str
    job_kind: str
    trigger: str
    account_id: int | None
    connection_id: int | None
    external_account_id: str
    cliente: str
    account_name: str
    marketplace: str
    region: str
    window_start: date | None
    window_end: date | None
    local_day: date | None
    status: str
    phase: str
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    deadline_at: datetime | None
    lease_holder: str
    lease_expires_at: datetime | None
    rows_written: int | None
    warning: str
    error_class: str
    error_message: str
    attempt_log: tuple[dict, ...]
    requested_by: str
    retry_of: int | None
    dedupe_key: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime | None
    params: dict = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @classmethod
    def from_row(cls, row: dict) -> SyncJob:
        return cls(
            id=int(row["id"]),
            integration_slug=row.get("integration_slug") or "",
            job_kind=row.get("job_kind") or "",
            trigger=row.get("trigger") or "",
            account_id=_optional_int(row.get("account_id")),
            connection_id=_optional_int(row.get("connection_id")),
            external_account_id=row.get("external_account_id") or "",
            cliente=row.get("cliente") or "",
            account_name=row.get("account_name") or "",
            marketplace=row.get("marketplace") or "",
            region=row.get("region") or "",
            window_start=parse_date(row.get("window_start")),
            window_end=parse_date(row.get("window_end")),
            local_day=parse_date(row.get("local_day")),
            status=row.get("status") or "",
            phase=row.get("phase") or "",
            attempts=int(row.get("attempts") or 0),
            max_attempts=int(row.get("max_attempts") or 0),
            next_attempt_at=parse_timestamp(row.get("next_attempt_at")),
            deadline_at=parse_timestamp(row.get("deadline_at")),
            lease_holder=row.get("lease_holder") or "",
            lease_expires_at=parse_timestamp(row.get("lease_expires_at")),
            rows_written=_optional_int(row.get("rows_written")),
            warning=row.get("warning") or "",
            error_class=row.get("error_class") or "",
            error_message=row.get("error_message") or "",
            attempt_log=tuple(row.get("attempt_log") or ()),
            requested_by=row.get("requested_by") or "",
            retry_of=_optional_int(row.get("retry_of")),
            dedupe_key=row.get("dedupe_key"),
            created_at=parse_timestamp(row.get("created_at")),
            started_at=parse_timestamp(row.get("started_at")),
            finished_at=parse_timestamp(row.get("finished_at")),
            updated_at=parse_timestamp(row.get("updated_at")),
            params=dict(row.get("params") or {}),
        )


@dataclass(frozen=True)
class NewSyncJob:
    integration_slug: str
    job_kind: str
    trigger: str
    external_account_id: str
    account_id: int | None
    connection_id: int | None
    cliente: str
    account_name: str
    marketplace: str
    region: str
    window_start: date | None
    window_end: date | None
    local_day: date | None
    deadline_at: datetime
    max_attempts: int
    dedupe_key: str | None
    requested_by: str = "scheduler"
    params: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        row = {
            "integration_slug": self.integration_slug,
            "job_kind": self.job_kind,
            "trigger": self.trigger,
            "external_account_id": self.external_account_id,
            "account_id": self.account_id,
            "connection_id": self.connection_id,
            "cliente": self.cliente,
            "account_name": self.account_name,
            "marketplace": self.marketplace,
            "region": self.region,
            "window_start": _iso(self.window_start),
            "window_end": _iso(self.window_end),
            "local_day": _iso(self.local_day),
            "deadline_at": _iso(self.deadline_at),
            "max_attempts": self.max_attempts,
            "dedupe_key": self.dedupe_key,
            "requested_by": self.requested_by,
        }
        # Only analysis jobs carry params; ingestion rows stay writable before migration 010 adds the column.
        if self.params:
            row["params"] = self.params
        return row


@dataclass(frozen=True)
class ManualRefresh:
    job_id: int | None
    created: bool
    reason: str


class SyncJobStore:
    def __init__(self, rest: _Rest):
        self._rest = rest

    def enqueue(self, job: NewSyncJob) -> bool:
        """False when a job with the same dedupe key already exists."""
        inserted = self._rest.insert_ignore(JOBS_TABLE, job.as_row(), on_conflict="dedupe_key")
        if inserted:
            log.info("sync job enqueued: %s %s %s (%s)", job.integration_slug, job.job_kind,
                     job.external_account_id, job.trigger)
        return inserted

    def claim_due(self, holder: str, limit: int, lease_seconds: int) -> list[SyncJob]:
        rows = self._rest.rpc(
            "claim_sync_jobs",
            {"p_holder": holder, "p_limit": limit, "p_lease_seconds": lease_seconds},
        )
        return [SyncJob.from_row(row) for row in rows or ()]

    def set_phase(self, job_id: int, phase: str, *, extend_lease_seconds: int | None = None) -> None:
        if phase not in PHASES:
            raise ValueError(f"unknown sync job phase: {phase!r}")
        changes: dict = {"phase": phase}
        if extend_lease_seconds is not None:
            lease_end = datetime.now(timezone.utc) + timedelta(seconds=extend_lease_seconds)
            changes["lease_expires_at"] = lease_end.isoformat()
        self._rest.update(JOBS_TABLE, {"id": f"eq.{job_id}"}, changes)

    def record_attempt_failure(self, job: SyncJob, *, error_class: str, message: str,
                               retryable: bool, now: datetime) -> SyncJob:
        attempts = job.attempts + 1
        message = message[:_MESSAGE_MAX_CHARS]
        attempt_log = job.attempt_log + (
            {"attempt": attempts, "at": now.isoformat(), "error_class": error_class, "message": message},
        )
        delay = RETRY_DELAYS_MIN[min(attempts - 1, len(RETRY_DELAYS_MIN) - 1)]
        next_attempt_at = now + timedelta(minutes=delay)
        will_retry = (
            retryable
            and attempts < job.max_attempts
            and (job.deadline_at is None or next_attempt_at < job.deadline_at)
        )
        updated = replace(
            job,
            status="retrying" if will_retry else "failed",
            phase="",
            attempts=attempts,
            attempt_log=attempt_log,
            error_class=error_class,
            error_message=message,
            next_attempt_at=next_attempt_at if will_retry else job.next_attempt_at,
            finished_at=None if will_retry else now,
            lease_holder="",
            lease_expires_at=None,
            updated_at=now,
        )
        changes = {
            "status": updated.status,
            "phase": "",
            "attempts": attempts,
            "attempt_log": list(attempt_log),
            "error_class": error_class,
            "error_message": message,
            "finished_at": _iso(updated.finished_at),
            "lease_holder": "",
            "lease_expires_at": None,
            "updated_at": now.isoformat(),
        }
        if will_retry:
            changes["next_attempt_at"] = next_attempt_at.isoformat()
        self._rest.update(JOBS_TABLE, _still_open(job.id), changes)
        log.warning("sync job %s attempt %d/%d failed (%s): %s -> %s", job.id, attempts,
                    job.max_attempts, error_class, message, updated.status)
        return updated

    def complete(self, job: SyncJob, *, rows_written: int, warning: str = "", now: datetime) -> None:
        changes = {
            "status": "completed",
            "phase": "",
            "finished_at": now.isoformat(),
            "rows_written": rows_written,
            "warning": warning,
            "error_class": "",
            "error_message": "",
            "lease_holder": "",
            "lease_expires_at": None,
            "updated_at": now.isoformat(),
        }
        if job.trigger in _RELEASES_DEDUPE_ON_COMPLETE:
            changes["dedupe_key"] = None
        self._rest.update(JOBS_TABLE, _still_open(job.id), changes)
        log.info("sync job %s completed: %d rows%s", job.id, rows_written,
                 f" ({warning})" if warning else "")

    def fail_expired(self, now: datetime) -> int:
        """Jobs that can no longer finish in time become failures.

        Queued jobs fail at their deadline. A running job fails once its lease lapsed and
        its deadline passed more than `RUNNING_DEADLINE_GRACE` ago: nothing reclaims it then.
        """
        queued = "in.(pending,retrying)"
        lease_lapsed = f"lt.{now.isoformat()}"
        passes = (
            ({"status": queued, "deadline_at": f"lte.{now.isoformat()}"}, {"status": queued}),
            ({"status": "eq.running", "lease_expires_at": lease_lapsed,
              "deadline_at": f"lt.{(now - RUNNING_DEADLINE_GRACE).isoformat()}"},
             {"status": "eq.running", "lease_expires_at": lease_lapsed}),
        )
        failed_ids: list[int] = []
        for candidates, still_expired in passes:
            job_ids = [int(row["id"]) for row in self._rest.select(JOBS_TABLE, {"select": "id", **candidates})]
            if not job_ids:
                continue
            # A job claimed or closed between the select and this update must be left alone.
            self._rest.update(
                JOBS_TABLE,
                {"id": _in_filter(job_ids), **still_expired},
                {
                    "status": "failed",
                    "phase": "",
                    "error_class": "deadline",
                    "error_message": _DEADLINE_MESSAGE,
                    "lease_holder": "",
                    "lease_expires_at": None,
                    "finished_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
            )
            failed_ids.extend(job_ids)
        if failed_ids:
            log.warning("sync jobs past their deadline marked failed: %s", failed_ids)
        return len(failed_ids)

    def cancel_open_for_profile(self, slug: str, external_account_id: str, reason: str) -> int:
        open_filter = _in_filter(OPEN_STATUSES)
        rows = self._rest.select(
            JOBS_TABLE,
            {
                "select": "id",
                "integration_slug": f"eq.{slug}",
                "external_account_id": f"eq.{external_account_id}",
                "status": open_filter,
            },
        )
        job_ids = [int(row["id"]) for row in rows]
        if not job_ids:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        self._rest.update(
            JOBS_TABLE,
            {"id": _in_filter(job_ids), "status": open_filter},
            {
                "status": "cancelled",
                "phase": "",
                "error_message": reason[:_MESSAGE_MAX_CHARS],
                "lease_holder": "",
                "lease_expires_at": None,
                "finished_at": now,
                "updated_at": now,
            },
        )
        log.info("cancelled %d open %s jobs for %s: %s", len(job_ids), slug, external_account_id, reason)
        return len(job_ids)

    def has_open(self, slug: str, job_kind: str, external_account_id: str) -> bool:
        rows = self._rest.select(
            JOBS_TABLE,
            {
                "select": "id",
                "integration_slug": f"eq.{slug}",
                "job_kind": f"eq.{job_kind}",
                "external_account_id": f"eq.{external_account_id}",
                "status": _in_filter(OPEN_STATUSES),
                "limit": "1",
            },
        )
        return bool(rows)

    def list_recent(self, *, slugs: tuple[str, ...] = (), statuses: tuple[str, ...] = (),
                    external_account_id: str = "", since: datetime | None = None,
                    only_problems: bool = False, limit: int = 200,
                    before_id: int | None = None) -> list[SyncJob]:
        """Newest first. Pass the last id of a page as `before_id` for the next one."""
        params: dict = {"select": "*", "order": "id.desc", "limit": str(limit)}
        if slugs:
            params["integration_slug"] = _in_filter(slugs)
        if statuses:
            params["status"] = _in_filter(statuses)
        if external_account_id:
            params["external_account_id"] = f"eq.{external_account_id}"
        if since is not None:
            params["created_at"] = f"gte.{since.isoformat()}"
        if only_problems:
            params["or"] = _PROBLEM_FILTER
        if before_id is not None:
            params["id"] = f"lt.{before_id}"
        return [SyncJob.from_row(row) for row in self._rest.select(JOBS_TABLE, params)]

    def get(self, job_id: int) -> SyncJob | None:
        rows = self._rest.select(JOBS_TABLE, {"select": "*", "id": f"eq.{job_id}", "limit": "1"})
        return SyncJob.from_row(rows[0]) if rows else None

    def latest_for_profile(self, external_account_id: str,
                           job_kind: str = "sp_search_terms") -> SyncJob | None:
        rows = self._rest.select(
            JOBS_TABLE,
            {
                "select": "*",
                "external_account_id": f"eq.{external_account_id}",
                "job_kind": f"eq.{job_kind}",
                "order": "created_at.desc,id.desc",
                "limit": "1",
            },
        )
        return SyncJob.from_row(rows[0]) if rows else None

    def counts_since(self, since: datetime) -> dict[str, int]:
        rows = self._rest.select(
            JOBS_TABLE, {"select": "status", "created_at": f"gte.{since.isoformat()}"}
        )
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return counts

    def request_manual_refresh(self, profile_id: str, requested_by: str) -> ManualRefresh:
        try:
            rows = self._rest.rpc(
                "request_manual_refresh",
                {"p_profile_id": profile_id, "p_requested_by": requested_by},
            )
        except Exception as exc:
            raise StoreError(_error_message(exc, "pedir la actualización")) from exc
        answer = rows[0] if isinstance(rows, list) and rows else {}
        outcome = ManualRefresh(
            job_id=_optional_int(answer.get("job_id")),
            created=bool(answer.get("created")),
            reason=answer.get("reason") or "profile_unavailable",
        )
        log.info("manual refresh for %s by %s: %s (job %s)", profile_id, requested_by,
                 outcome.reason, outcome.job_id)
        return outcome

    def retry(self, job_id: int, actor: str) -> int | None:
        """The new job's id, or None when the job is not failed or cancelled or its Amazon profile is not active."""
        try:
            new_job_id = self._rest.rpc("retry_sync_job", {"p_job_id": job_id, "p_actor": actor})
        except Exception as exc:
            raise StoreError(_error_message(exc, "reintentar la solicitud")) from exc
        log.info("retry of sync job %s by %s -> %s", job_id, actor, new_job_id)
        return _optional_int(new_job_id)

    def cancel(self, job_id: int, actor: str) -> bool:
        try:
            cancelled = self._rest.rpc("cancel_sync_job", {"p_job_id": job_id, "p_actor": actor})
        except Exception as exc:
            raise StoreError(_error_message(exc, "cancelar la solicitud")) from exc
        log.info("cancel of sync job %s by %s -> %s", job_id, actor, cancelled)
        return bool(cancelled)


def sanitize_error(exc: BaseException) -> tuple[str, str]:
    """(error_class, message) safe to persist: no query strings, tokens or long hex."""
    message = str(exc)
    message = _URL_QUERY.sub(r"\1", message)
    message = _BEARER.sub("Bearer [redacted]", message)
    message = _LWA_TOKEN.sub("[redacted]", message)
    message = _SECRET_PARAM.sub(r"\1=[redacted]", message)
    message = _LONG_HEX.sub("[hex]", message)
    message = " ".join(message.split())
    return type(exc).__name__, message[:_MESSAGE_MAX_CHARS]


def parse_date(raw) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw)[:10])


def parse_timestamp(raw) -> datetime | None:
    if not raw:
        return None
    parsed = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _optional_int(raw) -> int | None:
    return int(raw) if raw is not None else None


def _iso(moment: date | datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def _in_filter(values) -> str:
    return f"in.({','.join(str(value) for value in values)})"


def _still_open(job_id: int) -> dict:
    """An admin may cancel a job whose lease lapsed; a late write from the worker must not reopen it."""
    return {"id": f"eq.{job_id}", "status": _in_filter(OPEN_STATUSES)}

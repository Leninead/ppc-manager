"""One tick of the Amazon Ads search term sync: plan jobs, request reports, poll, save, close.

Every step is isolated per profile, job and report: a failure is recorded and the tick goes on.
"""
from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

import requests

from core.amazon_ads import ad_entities, report_kinds
from core.amazon_ads.api_client import AdsAccessDenied, AdsApiClient, AdsThrottled
from core.amazon_ads.campaign_entities import fetch_campaigns, save_campaigns
from core.amazon_ads.portfolios import fetch_portfolios, save_portfolios
from core.amazon_ads.raw_reports import (
    REPORT_REQUESTS_TABLE,
    StoredRaw,
    _unlink_raw,
    prune_expired,
    raw_relative_path,
    store_download,
)
from core.amazon_ads.report_fetcher import RETENTION_DAYS, ReportFailed, ReportFetcher, ReportStatus
from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    CAMPAIGNS_KIND,
    CHUNK_DAYS,
    DAILY_WINDOW_DAYS,
    PORTFOLIOS_KIND,
    PRODUCT_KINDS,
    PRODUCT_REPORT_KINDS,
    PROFILE_ACTIVE,
    PROFILE_INACTIVE,
    PROFILE_NEEDS_REAUTH,
    SB_ENTITIES_KIND,
    SD_ENTITIES_KIND,
    SEARCH_TERMS_KIND,
    SP_TARGETS_KIND,
    ProfileState,
    backfill_dedupe_prefix,
    chunk_days_for,
    is_backfill,
    is_product_history,
    plan_jobs,
    profile_timezone,
    report_chunks,
)
from core.amazon_ads.tokens import ConnectionUnavailable, TokenManager
from core.integrations import oauth
from core.integrations.amazon_identity import SLUG
from core.integrations.store import ACCOUNTS_TABLE, ACTIVE_STATUS, CONNECTIONS_TABLE, NEEDS_REAUTH, _Rest
from core.integrations.sync_jobs import (
    JOBS_TABLE,
    OPEN_STATUSES,
    SyncJob,
    SyncJobStore,
    _in_filter,
    parse_date,
    parse_timestamp,
    sanitize_error,
)

log = logging.getLogger(__name__)

PROFILE_SYNC_TABLE = "ads_profile_sync"
HEARTBEATS_TABLE = "integration_worker_heartbeats"
IMAGE_TAG_ENV = "IMAGE_TAG"
JOB_CLAIM_LIMIT = 20
LEASE_SECONDS = 900
FIRST_POLL_DELAY_SECONDS = 60
MAX_POLL_DELAY_SECONDS = 600
REPORT_MAX_WAIT = timedelta(hours=3, minutes=20)
THROTTLE_PAUSE = timedelta(minutes=5)
PRUNE_INTERVAL = timedelta(hours=1)
REPLACE_DAY_TIMEOUT_SECONDS = 120
# Saves are the slow part of a tick; capping them keeps a tick inside the 5-minute silent-worker alert.
MAX_SAVES_PER_TICK = 4
# A save that was cut off this many times (an out-of-memory kill, most likely) is not tried again.
MAX_SAVE_ATTEMPTS = 2
MAX_HEARTBEAT_ERRORS = 20
EMPTY_DAY_KEPT = -1
MAX_LISTED_EMPTY_DAYS = 5

NO_PORTFOLIO_ACCESS_WARNING = "sin permiso para leer portfolios"
NO_CAMPAIGN_ACCESS_WARNING = "sin permiso para leer campañas"
NO_TARGETS_ACCESS_WARNING = "sin permiso para leer keywords y targets"
NO_SB_ACCESS_WARNING = "sin acceso a Sponsored Brands"
NO_SD_ACCESS_WARNING = "sin acceso a Sponsored Display"
# How recently the SB list must have shown a campaign of the old format for v2 to be asked for it.
LEGACY_SB_SEEN_WITHIN = timedelta(days=2)
PROFILE_INACTIVE_REASON = "cancelada: el perfil ya no está conectado"
CLOSED_JOB_MESSAGE = "la solicitud se cerró antes de terminar este tramo"
SAVE_CRASHED_MESSAGE = "El guardado de este tramo se cortó dos veces; revisá el tamaño del reporte."

_PROFILE_STATUS_BY_CONNECTION = {ACTIVE_STATUS: PROFILE_ACTIVE, NEEDS_REAUTH: PROFILE_NEEDS_REAUTH}
_ACCOUNT_COLUMNS = "id,nombre_externo,tipo,region,cliente,connection_id,profiles"
_JOB_FLAG_COLUMNS = ("id,job_kind,trigger,external_account_id,status,local_day,window_start,window_end,dedupe_key,"
                     "rows_written")
# The triggers a job that loaded a report's whole history can carry: the planner's, or a manual retry of it.
_HISTORY_TRIGGERS = "in.(backfill,retry)"
_CLOSED_JOB_STATUSES = "in.(failed,cancelled)"
_UNFINISHED_REQUEST_STATUSES = frozenset({"to_request", "requested", "saving"})
_REQUEST_RETRY_RESET = {
    "status": "to_request",
    "amazon_report_id": "",
    "amazon_status": "",
    "requested_at": None,
    "next_poll_at": None,
    "poll_count": 0,
    "save_attempts": 0,
    "lease_holder": "",
    "lease_expires_at": None,
    "error_class": "",
    "error_message": "",
    "raw_status": "none",
    "raw_path": "",
    "raw_bytes": None,
    "raw_sha256": "",
}
_LEASE_RELEASE = {"lease_holder": "", "lease_expires_at": None}


class InvalidSyncJob(ValueError):
    """The stored job cannot run at all: unknown kind, no window, or a window past Amazon's retention."""


class ReportTimedOut(RuntimeError):
    """Amazon did not finish a report within the wait this pipeline allows."""


class SaveCrashed(RuntimeError):
    """Saving this report chunk was cut off `MAX_SAVE_ATTEMPTS` times, so trying again would only repeat it."""


@dataclass
class TickSummary:
    profiles_active: int = 0
    jobs_planned: int = 0
    reports_created: int = 0
    reports_polled: int = 0
    reports_saved: int = 0
    rows_written: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    raw_pruned: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def is_idle(self) -> bool:
        return not (self.jobs_planned or self.reports_created or self.reports_polled or self.reports_saved
                    or self.jobs_completed or self.jobs_failed or self.raw_pruned or self.errors)


def _never_stop() -> bool:
    return False


@dataclass
class _Tick:
    now: datetime
    summary: TickSummary
    stop_requested: Callable[[], bool] = _never_stop
    profiles: dict[str, dict] = field(default_factory=dict)
    jobs: dict[int, SyncJob] = field(default_factory=dict)
    # A 429 speaks for the whole app: once a step is throttled, no report kind continues it this tick.
    create_throttled: bool = False
    poll_throttled: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionJob:
    def __init__(
        self,
        *,
        rest: _Rest,
        jobs: SyncJobStore,
        tokens: TokenManager,
        raw_dir: Path,
        holder: str,
        api_factory: Callable[[str, int], AdsApiClient] | None = None,
        download_session: requests.Session | None = None,
        max_inflight_reports: int = 40,
        max_creates_per_tick: int = 12,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self._rest = rest
        self._jobs = jobs
        self._tokens = tokens
        self._raw_dir = Path(raw_dir)
        self._holder = holder
        self._api_factory = api_factory or self._token_backed_api
        self._download_session = download_session
        self._max_inflight_reports = max_inflight_reports
        self._max_creates_per_tick = max_creates_per_tick
        self._clock = clock
        self._amazon_clients: dict[tuple[str, int, str], tuple[AdsApiClient, ReportFetcher]] = {}
        self._last_prune_at: datetime | None = None

    def run_tick(self, now_utc: datetime, stop_requested: Callable[[], bool] = _never_stop) -> TickSummary:
        """`stop_requested` is checked between jobs, creates and saves; once true the tick only writes its heartbeat."""
        tick = _Tick(now=now_utc, summary=TickSummary(), stop_requested=stop_requested)
        try:
            tick.profiles = self._read_profiles()
        except Exception as exc:
            if _is_missing_table(exc):
                log.warning("amazon_ads: tables not migrated yet, nothing to sync")
                return TickSummary()
            # Planning or saving from an empty snapshot would backfill every profile again and drop currencies.
            self._record_error(tick, "read_profiles", exc)
            self._write_heartbeat_quietly(tick)
            return tick.summary

        steps = (
            ("sync_profiles", self._sync_profiles),
            ("plan", self._plan),
            ("start_jobs", self._start_jobs),
            ("create_reports", self._create_reports),
            ("poll_reports", self._poll_reports),
            ("finalize_jobs", self._finalize_jobs),
            ("prune_raw", self._prune_raw),
        )
        for step_name, step in steps:
            if tick.stop_requested():
                log.info("amazon_ads: stop requested, the tick ends before %s", step_name)
                break
            try:
                step(tick)
            except Exception as exc:
                self._record_error(tick, step_name, exc)
        self._write_heartbeat_quietly(tick)
        return tick.summary

    def _read_profiles(self) -> dict[str, dict]:
        rows = self._rest.select(PROFILE_SYNC_TABLE, {"select": "*"})
        return {str(row["profile_id"]): row for row in rows}

    def _sync_profiles(self, tick: _Tick) -> None:
        accounts = self._rest.select(ACCOUNTS_TABLE, {"select": _ACCOUNT_COLUMNS, "integration_slug": f"eq.{SLUG}"})
        connection_states = {
            int(row["id"]): row.get("estado") or ""
            for row in self._rest.select(CONNECTIONS_TABLE, {"select": "id,estado", "integration_slug": f"eq.{SLUG}"})
        }
        for connection_id, connection_state in connection_states.items():
            if connection_state != ACTIVE_STATUS:
                self._tokens.forget(connection_id)
        discovered = _discovered_profiles(accounts, connection_states)
        vanished = [
            profile_id for profile_id, row in tick.profiles.items()
            if profile_id not in discovered and row.get("status") != PROFILE_INACTIVE
        ]

        # Side effects first: if the status write below fails, the next tick sees the same change again.
        for profile_id, row in discovered.items():
            previous_status = (tick.profiles.get(profile_id) or {}).get("status")
            self._apply_status_change(tick, row, previous_status)
        for profile_id in vanished:
            self._apply_status_change(tick, {**tick.profiles[profile_id], "status": PROFILE_INACTIVE},
                                      tick.profiles[profile_id].get("status"))

        changed = [row for profile_id, row in discovered.items() if _profile_changed(tick.profiles.get(profile_id), row)]
        if changed:
            stamped = [{**row, "updated_at": tick.now.isoformat()} for row in changed]
            self._rest.upsert(PROFILE_SYNC_TABLE, stamped, on_conflict="profile_id")
        if vanished:
            self._rest.update(PROFILE_SYNC_TABLE, {"profile_id": _in_filter(vanished)}, {"status": PROFILE_INACTIVE})
        for row in changed:
            tick.profiles[row["profile_id"]] = {**tick.profiles.get(row["profile_id"], {}), **row}
        for profile_id in vanished:
            tick.profiles[profile_id]["status"] = PROFILE_INACTIVE

    def _apply_status_change(self, tick: _Tick, profile: dict, previous: str | None) -> None:
        profile_id, current = profile["profile_id"], profile["status"]
        if previous is None or previous == current:
            return
        try:
            if current == PROFILE_INACTIVE:
                self._jobs.cancel_open_for_profile(SLUG, profile_id, PROFILE_INACTIVE_REASON)
            elif current == PROFILE_ACTIVE:
                self._release_dedupe_keys(tick, profile)
        except Exception as exc:
            self._record_error(tick, f"profile {profile_id}", exc)

    def _release_dedupe_keys(self, tick: _Tick, profile: dict) -> None:
        """Jobs that failed while the authorization was broken still hold their keys and would block planning."""
        profile_id = str(profile["profile_id"])
        self._rest.update(
            JOBS_TABLE,
            {"dedupe_key": f"like.{backfill_dedupe_prefix(profile_id)}*", "status": _CLOSED_JOB_STATUSES},
            {"dedupe_key": None},
        )
        local_today = tick.now.astimezone(profile_timezone(profile.get("timezone") or "",
                                                           profile.get("region") or "")).date()
        self._rest.update(
            JOBS_TABLE,
            {"dedupe_key": f"like.{SLUG}:{profile_id}:*", "local_day": f"eq.{local_today.isoformat()}",
             "status": _CLOSED_JOB_STATUSES},
            {"dedupe_key": None},
        )

    def _plan(self, tick: _Tick) -> None:
        tick.summary.profiles_active = sum(1 for row in tick.profiles.values() if row.get("status") == PROFILE_ACTIVE)
        jobs_by_profile = self._recent_jobs_by_profile(tick.now)
        histories = self._product_histories()
        legacy_sb = self._profiles_with_legacy_sb(tick.now)
        for profile_id, row in tick.profiles.items():
            if row.get("status") != PROFILE_ACTIVE:
                continue
            try:
                state = _profile_state(row, jobs_by_profile.get(profile_id, ()), tick.now,
                                       histories.get(profile_id, frozenset()),
                                       has_legacy_sb=profile_id in legacy_sb)
                for new_job in plan_jobs(state, tick.now):
                    if self._jobs.enqueue(new_job):
                        tick.summary.jobs_planned += 1
            except Exception as exc:
                self._record_error(tick, f"plan {profile_id}", exc)
        tick.summary.jobs_failed += self._jobs.fail_expired(tick.now)

    def _recent_jobs_by_profile(self, now: datetime) -> dict[str, list[dict]]:
        query = {"select": _JOB_FLAG_COLUMNS, "integration_slug": f"eq.{SLUG}"}
        open_rows = self._rest.select(JOBS_TABLE, {**query, "status": _in_filter(OPEN_STATUSES)})
        # A profile-local day is never more than one day behind the UTC date.
        earliest_local_day = (now.date() - timedelta(days=1)).isoformat()
        recent_rows = self._rest.select(JOBS_TABLE, {**query, "local_day": f"gte.{earliest_local_day}"})
        rows_by_profile: dict[str, dict[int, dict]] = {}
        for row in (*open_rows, *recent_rows):
            rows_by_profile.setdefault(str(row.get("external_account_id") or ""), {})[int(row["id"])] = row
        return {profile_id: list(rows.values()) for profile_id, rows in rows_by_profile.items()}

    def _profiles_with_legacy_sb(self, now: datetime) -> frozenset[str]:
        """Profiles whose SB list still had campaigns of the old format in the last days: only those ask v2."""
        rows = self._rest.select(ad_entities.PRODUCT_CAMPAIGNS_TABLE, {
            "select": "profile_id",
            "ad_product": "eq.SB",
            "is_multi_ad_groups": "is.false",
            # Every listing rewrites seen_at, so an old-format campaign archived since has stopped being seen.
            "seen_at": f"gte.{(now - LEGACY_SB_SEEN_WITHIN).isoformat()}",
        })
        return frozenset(str(row.get("profile_id") or "") for row in rows)

    def _product_histories(self) -> dict[str, frozenset[str]]:
        """Per profile, the new report kinds whose whole history already loaded once."""
        rows = self._rest.select(JOBS_TABLE, {
            "select": "external_account_id,job_kind,window_start,window_end",
            "integration_slug": f"eq.{SLUG}",
            "job_kind": _in_filter(PRODUCT_REPORT_KINDS),
            "status": "eq.completed",
            "trigger": _HISTORY_TRIGGERS,
        })
        histories: dict[str, set[str]] = {}
        for row in rows:
            if is_product_history(row.get("job_kind") or "", parse_date(row.get("window_start")),
                                  parse_date(row.get("window_end"))):
                histories.setdefault(str(row.get("external_account_id") or ""), set()).add(row["job_kind"])
        return {profile_id: frozenset(kinds) for profile_id, kinds in histories.items()}

    def _start_jobs(self, tick: _Tick) -> None:
        for job in self._jobs.claim_due(self._holder, JOB_CLAIM_LIMIT, LEASE_SECONDS):
            if tick.stop_requested():
                # The rest keep their lease and are claimed again once it lapses.
                return
            tick.jobs[job.id] = job
            try:
                self._start_job(tick, job)
            except Exception as exc:
                try:
                    self._handle_job_error(tick, job, exc)
                except Exception as handler_exc:
                    # Unrecorded, the job is claimed again once its lease lapses; the rest of the batch still runs.
                    self._record_error(tick, f"job {job.id}", handler_exc)

    def _start_job(self, tick: _Tick, job: SyncJob) -> None:
        profile_status = (tick.profiles.get(job.external_account_id) or {}).get("status")
        if profile_status != PROFILE_ACTIVE:
            raise ConnectionUnavailable(
                f"profile {job.external_account_id} is {profile_status or 'not synced'}, not active"
            )
        if job.job_kind == PORTFOLIOS_KIND:
            self._refresh_portfolios(tick, job)
        elif job.job_kind == CAMPAIGN_ENTITIES_KIND:
            self._refresh_campaign_entities(tick, job)
        elif job.job_kind == SP_TARGETS_KIND:
            self._refresh_sp_targets(tick, job)
        elif job.job_kind in (SB_ENTITIES_KIND, SD_ENTITIES_KIND):
            self._refresh_product_entities(tick, job)
        elif (kind := report_kinds.by_job_kind(job.job_kind)) is not None:
            self._prepare_report_requests(tick, job, kind)
        else:
            raise InvalidSyncJob(f"job {job.id} has an unknown kind {job.job_kind!r}")

    def _refresh_portfolios(self, tick: _Tick, job: SyncJob) -> None:
        api, _ = self._amazon(job)
        try:
            portfolios = fetch_portfolios(api, job.external_account_id)
        except AdsAccessDenied:
            log.info("amazon_ads: profile %s may not list portfolios", job.external_account_id)
            self._complete(tick, job, rows_written=0, warning=NO_PORTFOLIO_ACCESS_WARNING)
            return
        saved_count = save_portfolios(self._rest, job.external_account_id, portfolios, tick.now)
        self._complete(tick, job, rows_written=saved_count)

    def _refresh_campaign_entities(self, tick: _Tick, job: SyncJob) -> None:
        api, _ = self._amazon(job)
        try:
            campaigns = fetch_campaigns(api, job.external_account_id)
        except AdsAccessDenied:
            log.info("amazon_ads: profile %s may not list campaigns", job.external_account_id)
            self._complete(tick, job, rows_written=0, warning=NO_CAMPAIGN_ACCESS_WARNING)
            return
        saved_count = save_campaigns(self._rest, job.external_account_id, campaigns, tick.now)
        self._complete(tick, job, rows_written=saved_count)

    def _refresh_sp_targets(self, tick: _Tick, job: SyncJob) -> None:
        api, _ = self._amazon(job)
        try:
            targets = ad_entities.fetch_sp_targets(api, job.external_account_id)
        except AdsAccessDenied:
            log.info("amazon_ads: profile %s may not list keywords and targets", job.external_account_id)
            self._complete(tick, job, rows_written=0, warning=NO_TARGETS_ACCESS_WARNING)
            return
        saved_count = ad_entities.save_targets(self._rest, job.external_account_id, "SP", targets, tick.now)
        self._complete(tick, job, rows_written=saved_count)

    def _refresh_product_entities(self, tick: _Tick, job: SyncJob) -> None:
        """Sponsored Brands or Display: campaigns first, then their targets.

        The rows written are the campaigns: the planner asks this product's reports only when there are some,
        so an account without the program is never asked for reports it would refuse every night.
        """
        is_brands = job.job_kind == SB_ENTITIES_KIND
        ad_product = "SB" if is_brands else "SD"
        api, _ = self._amazon(job)
        try:
            if is_brands:
                campaigns = ad_entities.fetch_sb_campaigns(api, job.external_account_id)
                targets = ad_entities.fetch_sb_targets(api, job.external_account_id) if campaigns else []
            else:
                campaigns = ad_entities.fetch_sd_campaigns(api, job.external_account_id)
                targets = ad_entities.fetch_sd_targets(api, job.external_account_id) if campaigns else []
        except AdsAccessDenied:
            log.info("amazon_ads: profile %s has no %s access", job.external_account_id, ad_product)
            self._complete(tick, job, rows_written=0,
                           warning=NO_SB_ACCESS_WARNING if is_brands else NO_SD_ACCESS_WARNING)
            return
        saved_count = ad_entities.save_product_campaigns(self._rest, job.external_account_id, campaigns, tick.now)
        ad_entities.save_targets(self._rest, job.external_account_id, ad_product, targets, tick.now)
        self._complete(tick, job, rows_written=saved_count)

    def _prepare_report_requests(self, tick: _Tick, job: SyncJob, kind: report_kinds.ReportKind) -> None:
        """Idempotent, so a job claimed again after its worker died resumes from the chunks it already has."""
        existing = self._rest.select(REPORT_REQUESTS_TABLE, {"select": "id,status,raw_status,raw_path",
                                                             "job_id": f"eq.{job.id}"})
        if not existing:
            chunk_days = kind.chunk_days or self._chunk_days(job.external_account_id)
            self._rest.insert(REPORT_REQUESTS_TABLE, [
                {
                    "job_id": job.id,
                    "profile_id": job.external_account_id,
                    "report_kind": kind.name,
                    "window_start": chunk_start.isoformat(),
                    "window_end": chunk_end.isoformat(),
                }
                for chunk_start, chunk_end in self._requestable_chunks(tick, job, chunk_days)
            ])
            self._renew_job_lease(tick, job, "requesting")
            return
        failed = [row for row in existing if row.get("status") == "failed"]
        if failed:
            self._reset_failed_requests(failed)
        if all(row.get("status") == "saved" for row in existing):
            return
        has_chunks_to_request = bool(failed) or any(row.get("status") == "to_request" for row in existing)
        self._renew_job_lease(tick, job, "requesting" if has_chunks_to_request else "waiting")

    def _reset_failed_requests(self, failed_requests: list[dict]) -> None:
        for request in failed_requests:
            # A retried chunk writes a new raw file; one left behind by the failed attempt would never be pruned.
            if request.get("raw_status") == "kept" and request.get("raw_path"):
                _unlink_raw(self._raw_dir, str(request["raw_path"]), request.get("id"))
        self._rest.update(REPORT_REQUESTS_TABLE, {"id": _in_filter(_request_ids(failed_requests)),
                                                  "status": "eq.failed"}, _REQUEST_RETRY_RESET)

    def _chunk_days(self, profile_id: str) -> int:
        latest_saved = self._rest.select(REPORT_REQUESTS_TABLE, {
            "select": "row_count,window_start,window_end",
            "profile_id": f"eq.{profile_id}",
            "status": "eq.saved",
            "order": "saved_at.desc",
            "limit": "1",
        })
        if not latest_saved:
            return CHUNK_DAYS
        latest = latest_saved[0]
        window_days = (parse_date(latest["window_end"]) - parse_date(latest["window_start"])).days + 1
        return chunk_days_for(int(latest.get("row_count") or 0) / window_days)

    def _requestable_chunks(self, tick: _Tick, job: SyncJob, chunk_days: int) -> list[tuple[date, date]]:
        if job.window_start is None or job.window_end is None:
            raise InvalidSyncJob(f"job {job.id} has no report window")
        first_day = max(job.window_start, self._earliest_retained_day(tick, job))
        if first_day > job.window_end:
            raise InvalidSyncJob(
                f"job {job.id} window {job.window_start}..{job.window_end} is past Amazon's {_retention_days(job)}-day retention"
            )
        return report_chunks(first_day, job.window_end, chunk_days)

    def _create_reports(self, tick: _Tick) -> None:
        for kind in report_kinds.ALL:
            if tick.stop_requested() or tick.create_throttled:
                return
            self._create_reports_of(tick, kind)

    def _create_reports_of(self, tick: _Tick, kind: report_kinds.ReportKind) -> None:
        max_inflight = _capped(kind.max_inflight_reports, self._max_inflight_reports)
        in_flight = self._rest.select(
            REPORT_REQUESTS_TABLE,
            {"select": "id", "status": "in.(requested,saving)", "report_kind": f"eq.{kind.name}",
             "limit": str(max_inflight)},
        )
        create_budget = min(_capped(kind.max_creates_per_tick, self._max_creates_per_tick),
                            max_inflight - len(in_flight))
        if create_budget <= 0:
            return
        claimed = self._claim_requests(("to_request",), create_budget, kind)
        jobs = self._jobs_of(tick, claimed)
        for position, request in enumerate(claimed):
            if tick.stop_requested():
                self._release_requests(claimed[position:])
                return
            job = jobs.get(int(request["job_id"]))
            if not self._job_accepts(tick, job, request):
                continue
            # Retention is judged now, not when the chunk was planned: a retried or delayed chunk can be days older.
            window_start = max(parse_date(request["window_start"]), self._earliest_retained_day(tick, job))
            window_end = parse_date(request["window_end"])
            if window_start > window_end:
                self._skip_past_retention(tick, job, request)
                continue
            if window_start != parse_date(request["window_start"]):
                self._rest.update(REPORT_REQUESTS_TABLE, {"id": f"eq.{request['id']}"},
                                  {"window_start": window_start.isoformat()})
            try:
                _, fetcher = self._amazon(job)
                report_id = fetcher.create(request["profile_id"], window_start, window_end)
            except AdsThrottled:
                log.warning("amazon_ads: report creation throttled, %d requests wait for the next tick",
                            len(claimed) - position)
                self._release_requests(claimed[position:])
                tick.create_throttled = True
                return
            except Exception as exc:
                self._fail_request(tick, job, request, exc)
                continue
            self._rest.update(REPORT_REQUESTS_TABLE, {"id": f"eq.{request['id']}"}, {
                "status": "requested",
                "amazon_report_id": report_id,
                "amazon_status": "",
                "requested_at": tick.now.isoformat(),
                "next_poll_at": (tick.now + timedelta(seconds=FIRST_POLL_DELAY_SECONDS)).isoformat(),
                "poll_count": 0,
                **_LEASE_RELEASE,
            })
            tick.summary.reports_created += 1
            self._renew_job_lease_quietly(tick, job, "waiting")

    def _skip_past_retention(self, tick: _Tick, job: SyncJob, request: dict) -> None:
        window_start, window_end = parse_date(request["window_start"]), parse_date(request["window_end"])
        days = [(window_start + timedelta(days=offset)).isoformat()
                for offset in range((window_end - window_start).days + 1)]
        self._rest.update(REPORT_REQUESTS_TABLE, {"id": f"eq.{request['id']}"}, {
            "status": "saved",
            "row_count": 0,
            "skipped_days": days,
            "saved_at": tick.now.isoformat(),
            "error_class": "",
            "error_message": "",
            **_LEASE_RELEASE,
        })
        log.info("amazon_ads: request %s (%s..%s) is past Amazon's %d-day retention, nothing left to request",
                 request["id"], window_start, window_end, _retention_days(job))
        self._renew_job_lease_quietly(tick, job)

    def _poll_reports(self, tick: _Tick) -> None:
        for kind in report_kinds.ALL:
            if tick.stop_requested() or tick.poll_throttled:
                return
            self._poll_reports_of(tick, kind)

    def _poll_reports_of(self, tick: _Tick, kind: report_kinds.ReportKind) -> None:
        claimed = self._claim_requests(("requested", "saving"),
                                       _capped(kind.max_inflight_reports, self._max_inflight_reports), kind)
        jobs = self._jobs_of(tick, claimed)
        saves_started = 0
        max_saves = _capped(kind.max_saves_per_tick, MAX_SAVES_PER_TICK)
        for position, request in enumerate(claimed):
            if saves_started >= max_saves or tick.stop_requested():
                self._release_requests(claimed[position:])
                return
            job = jobs.get(int(request["job_id"]))
            if not self._job_accepts(tick, job, request):
                continue
            try:
                if request.get("status") == "saving" and int(request.get("save_attempts") or 0) >= MAX_SAVE_ATTEMPTS:
                    raise SaveCrashed(SAVE_CRASHED_MESSAGE)
                _, fetcher = self._amazon(job)
                report = fetcher.status(request["profile_id"], request["amazon_report_id"])
                tick.summary.reports_polled += 1
                if report.status == "COMPLETED":
                    saves_started += 1
                    self._save_report(tick, job, request, fetcher, report)
                else:
                    self._wait_for_report(tick, request, report)
            except AdsThrottled:
                log.warning("amazon_ads: report polling throttled, pausing %d requests", len(claimed) - position)
                self._rest.update(REPORT_REQUESTS_TABLE, {"id": _in_filter(_request_ids(claimed[position:]))},
                                  {"next_poll_at": (tick.now + THROTTLE_PAUSE).isoformat(), **_LEASE_RELEASE})
                tick.poll_throttled = True
                return
            except Exception as exc:
                self._fail_request(tick, job, request, exc)

    def _wait_for_report(self, tick: _Tick, request: dict, report: ReportStatus) -> None:
        if report.status == "FAILED":
            raise ReportFailed(f"Amazon could not build report {report.report_id}: "
                               f"{report.failure_reason or 'no reason given'}", amazon_status=report.status)
        if self._waited_too_long(tick, request):
            raise ReportTimedOut(f"report {report.report_id} still {report.status} after {REPORT_MAX_WAIT}")
        poll_count = int(request.get("poll_count") or 0)
        delay_seconds = min(FIRST_POLL_DELAY_SECONDS * 2 ** poll_count, MAX_POLL_DELAY_SECONDS)
        self._rest.update(REPORT_REQUESTS_TABLE, {"id": f"eq.{request['id']}"}, {
            "status": "requested",
            "amazon_status": report.status,
            "poll_count": poll_count + 1,
            "next_poll_at": (tick.now + timedelta(seconds=delay_seconds)).isoformat(),
            **_LEASE_RELEASE,
        })

    def _save_report(self, tick: _Tick, job: SyncJob, request: dict, fetcher: ReportFetcher,
                     report: ReportStatus) -> None:
        request_filter = {"id": f"eq.{request['id']}"}
        save_attempts = int(request.get("save_attempts") or 0)
        # Counted before the download: a save killed halfway leaves the row 'saving' with this count behind.
        self._rest.update(REPORT_REQUESTS_TABLE, request_filter,
                          {"status": "saving", "amazon_status": report.status, "save_attempts": save_attempts + 1})
        self._renew_job_lease(tick, job, "saving")
        requested_at = parse_timestamp(request.get("requested_at")) or tick.now
        relative_path = raw_relative_path(request["profile_id"], request["amazon_report_id"], requested_at.date())

        with tempfile.TemporaryDirectory(prefix="ads_raw_") as fallback_dir:
            try:
                stored, raw_status, stored_root = self._store_raw(relative_path, fetcher, report.url, Path(fallback_dir))
            except ReportFailed:
                if self._waited_too_long(tick, request):
                    raise
                log.info("amazon_ads: download link of report %s expired, polling again", report.report_id)
                self._rest.update(REPORT_REQUESTS_TABLE, request_filter, {
                    "status": "requested",
                    "save_attempts": save_attempts,
                    "next_poll_at": (tick.now + timedelta(seconds=FIRST_POLL_DELAY_SECONDS)).isoformat(),
                    **_LEASE_RELEASE,
                })
                self._renew_job_lease_quietly(tick, job, "waiting")
                return
            stored_path = stored_root / stored.relative_path
            try:
                rows_written, empty_days = self._replace_days(tick, request, stored_path)
            except Exception:
                if raw_status == "kept":
                    _discard_raw(stored_path)
                raise

        self._rest.update(REPORT_REQUESTS_TABLE, request_filter, {
            "status": "saved",
            "row_count": rows_written,
            "skipped_days": [day.isoformat() for day in empty_days],
            "saved_at": tick.now.isoformat(),
            "raw_status": raw_status,
            "raw_path": stored.relative_path if raw_status == "kept" else "",
            "raw_bytes": stored.size_bytes,
            "raw_sha256": stored.sha256,
            "error_class": "",
            "error_message": "",
            **_LEASE_RELEASE,
        })
        tick.summary.reports_saved += 1
        tick.summary.rows_written += rows_written
        self._renew_job_lease_quietly(tick, job, "waiting")

    def _store_raw(self, relative_path: str, fetcher: ReportFetcher, url: str,
                   fallback_root: Path) -> tuple[StoredRaw, str, Path]:
        def write_body(target: BinaryIO) -> int:
            return fetcher.download(url, target)

        try:
            return store_download(self._raw_dir, relative_path, write_body), "kept", self._raw_dir
        except OSError as exc:
            log.error("amazon_ads: cannot write raw reports under %s (%s); saving %s without keeping the file",
                      self._raw_dir, exc, relative_path)
            return store_download(fallback_root, relative_path, write_body), "write_failed", fallback_root

    def _replace_days(self, tick: _Tick, request: dict, stored_path: Path) -> tuple[int, list[date]]:
        profile_id = request["profile_id"]
        kind = report_kinds.by_name(request.get("report_kind"))
        currency_code = (tick.profiles.get(profile_id) or {}).get("currency_code") or ""
        report_rows: list[tuple | None] = kind.load_compact_report(stored_path)
        positions_by_day = kind.day_row_positions(report_rows, window_start=parse_date(request["window_start"]),
                                                  window_end=parse_date(request["window_end"]))
        rows_written = 0
        empty_days: list[date] = []
        # One day at a time, so only that day's rows are ever held in their table shape.
        for day in sorted(positions_by_day):
            positions = positions_by_day.pop(day)
            rows = kind.day_rows(report_rows, positions, profile_id=profile_id,
                                 currency_code=currency_code, day=day)
            for position in positions:
                report_rows[position] = None
            inserted = self._rest.rpc(
                kind.replace_day_rpc,
                {"p_profile_id": profile_id, "p_day": day.isoformat(), "p_rows": rows, **kind.rpc_args},
                timeout_s=REPLACE_DAY_TIMEOUT_SECONDS,
            )
            del rows
            if inserted == EMPTY_DAY_KEPT:
                empty_days.append(day)
            else:
                rows_written += int(inserted or 0)
        return rows_written, empty_days

    def _finalize_jobs(self, tick: _Tick) -> None:
        running_jobs = [
            SyncJob.from_row(row)
            for row in self._rest.select(JOBS_TABLE, {
                "select": "*",
                "integration_slug": f"eq.{SLUG}",
                "job_kind": _in_filter(report_kinds.REPORT_JOB_KINDS),
                "status": "eq.running",
            })
        ]
        if not running_jobs:
            return
        chunk_rows = self._rest.select(REPORT_REQUESTS_TABLE, {
            "select": "job_id,status,window_start,window_end,row_count,skipped_days,error_class,error_message",
            "job_id": _in_filter([job.id for job in running_jobs]),
        })
        chunks_by_job: dict[int, list[dict]] = {}
        for chunk in chunk_rows:
            chunks_by_job.setdefault(int(chunk["job_id"]), []).append(chunk)
        for job in running_jobs:
            chunks = chunks_by_job.get(job.id, [])
            statuses = {chunk.get("status") for chunk in chunks}
            try:
                if statuses == {"saved"}:
                    self._close_report_job(tick, job, chunks)
                elif "failed" in statuses and not statuses & _UNFINISHED_REQUEST_STATUSES:
                    self._record_unrecorded_chunk_failure(tick, job, chunks)
            except Exception as exc:
                self._record_error(tick, f"finalize job {job.id}", exc)

    def _record_unrecorded_chunk_failure(self, tick: _Tick, job: SyncJob, chunks: list[dict]) -> None:
        """A chunk failed but its job attempt was lost to a failed write or a crash; nothing else would retry it."""
        failed_chunk = next(chunk for chunk in chunks if chunk.get("status") == "failed")
        tick.jobs[job.id] = job
        self._record_job_failure(tick, job, failed_chunk.get("error_class") or "ReportFailed",
                                 failed_chunk.get("error_message") or "", retryable=True)

    def _close_report_job(self, tick: _Tick, job: SyncJob, chunks: list[dict]) -> None:
        # ads_profile_sync is the STR picker's freshness; a campaign job must never move it.
        if job.job_kind == SEARCH_TERMS_KIND:
            # The profile goes first: if completing the job then fails, the next tick redoes both safely.
            self._update_profile(tick, job.external_account_id, self._success_changes(tick, job, chunks))
        empty_days = sorted({str(day) for chunk in chunks for day in chunk.get("skipped_days") or ()})
        rows_written = sum(int(chunk.get("row_count") or 0) for chunk in chunks)
        self._complete(tick, job, rows_written=rows_written, warning=_empty_days_warning(empty_days))

    def _success_changes(self, tick: _Tick, job: SyncJob, chunks: list[dict]) -> dict:
        profile = tick.profiles.get(job.external_account_id) or {}
        known_from = parse_date(profile.get("data_from"))
        known_through = parse_date(profile.get("data_through"))
        covered_from = min(parse_date(chunk["window_start"]) for chunk in chunks)
        covered_through = max(parse_date(chunk["window_end"]) for chunk in chunks)
        changes = {
            "data_from": min(day for day in (covered_from, known_from) if day).isoformat(),
            "data_through": max(day for day in (covered_through, known_through) if day).isoformat(),
            "last_success_at": tick.now.isoformat(),
            "last_error": "",
        }
        local_today = self._local_today(tick, job.external_account_id, job.region)
        window_days = (job.window_end - job.window_start).days + 1
        if window_days >= DAILY_WINDOW_DAYS and job.window_end == local_today - timedelta(days=1):
            changes["refreshed_on"] = local_today.isoformat()
        if is_backfill(job.trigger, job.window_start, job.window_end):
            changes["backfill_done_at"] = tick.now.isoformat()
        return changes

    def _prune_raw(self, tick: _Tick) -> None:
        last_prune_at = self._last_prune_at or self._stored_last_prune_at()
        if last_prune_at is not None and tick.now - last_prune_at < PRUNE_INTERVAL:
            self._last_prune_at = last_prune_at
            return
        tick.summary.raw_pruned = prune_expired(self._rest, self._raw_dir, tick.now)
        self._last_prune_at = tick.now

    def _stored_last_prune_at(self) -> datetime | None:
        rows = self._rest.select(HEARTBEATS_TABLE, {"select": "summary", "worker_name": f"eq.{SLUG}", "limit": "1"})
        return parse_timestamp(((rows[0].get("summary") or {}) if rows else {}).get("raw_pruned_at"))

    def _write_heartbeat(self, tick: _Tick) -> None:
        summary = asdict(tick.summary)
        summary["errors"] = summary["errors"][:MAX_HEARTBEAT_ERRORS]
        summary["raw_pruned_at"] = self._last_prune_at.isoformat() if self._last_prune_at else None
        self._rest.upsert(HEARTBEATS_TABLE, {
            "worker_name": SLUG,
            # When it is written, not when the tick started: a long tick is still a live worker.
            "last_tick_at": self._clock().isoformat(),
            "image_tag": os.environ.get(IMAGE_TAG_ENV, ""),
            "summary": summary,
        }, on_conflict="worker_name")

    def _write_heartbeat_quietly(self, tick: _Tick) -> None:
        try:
            self._write_heartbeat(tick)
        except Exception as exc:
            self._record_error(tick, "heartbeat", exc)

    def _handle_job_error(self, tick: _Tick, job: SyncJob, exc: Exception) -> None:
        if isinstance(exc, AdsThrottled):
            self._defer_throttled_job(tick, tick.jobs.get(job.id, job))
            return
        error_class, retryable = _classify(exc)
        _, message = sanitize_error(exc)
        self._record_job_failure(tick, job, error_class, message, retryable=retryable,
                                 needs_reauth=isinstance(exc, oauth.NeedsReauth))

    def _record_job_failure(self, tick: _Tick, job: SyncJob, error_class: str, message: str, *, retryable: bool,
                            needs_reauth: bool = False) -> None:
        current = tick.jobs.get(job.id, job)
        tick.summary.errors.append(f"job {job.id}: {error_class}: {message}")
        failed_for_good = False
        # A job already waiting for its retry redoes every failed chunk then; one more chunk is not a new attempt.
        if current.is_open and not (retryable and current.status != "running"):
            updated = self._jobs.record_attempt_failure(current, error_class=error_class, message=message,
                                                        retryable=retryable, now=tick.now)
            tick.jobs[job.id] = updated
            failed_for_good = updated.status == "failed"
            tick.summary.jobs_failed += int(failed_for_good)
        else:
            log.warning("amazon_ads: job %s (%s) failed again before its retry: %s: %s", job.id, current.status,
                        error_class, message)

        profile_changes: dict = {}
        if needs_reauth:
            profile_changes["status"] = PROFILE_NEEDS_REAUTH
        if profile_changes or (failed_for_good and job.job_kind == SEARCH_TERMS_KIND):
            profile_changes.update(last_error=message, last_failure_at=tick.now.isoformat())
            self._update_profile_quietly(tick, job.external_account_id, profile_changes)

    def _defer_throttled_job(self, tick: _Tick, job: SyncJob) -> None:
        if job.status != "running":
            return
        next_attempt_at = tick.now + THROTTLE_PAUSE
        self._rest.update(JOBS_TABLE, {"id": f"eq.{job.id}"}, {
            "status": "retrying", "phase": "", "next_attempt_at": next_attempt_at.isoformat(), **_LEASE_RELEASE,
        })
        tick.jobs[job.id] = replace(job, status="retrying", phase="", next_attempt_at=next_attempt_at,
                                    lease_holder="", lease_expires_at=None)
        log.warning("amazon_ads: job %s throttled, retrying at %s without spending an attempt", job.id,
                    next_attempt_at.isoformat())

    def _fail_request(self, tick: _Tick, job: SyncJob, request: dict, exc: Exception) -> None:
        # The job's transition first: a chunk marked failed under a job still running would leave that job stranded.
        self._handle_job_error(tick, job, exc)
        error_class, message = sanitize_error(exc)
        changes = {"status": "failed", "error_class": error_class, "error_message": message, **_LEASE_RELEASE}
        if isinstance(exc, ReportFailed) and exc.amazon_status:
            changes["amazon_status"] = exc.amazon_status
        self._rest.update(REPORT_REQUESTS_TABLE, {"id": f"eq.{request['id']}"}, changes)

    def _job_accepts(self, tick: _Tick, job: SyncJob | None, request: dict) -> bool:
        if job is not None and tick.jobs.get(job.id, job).is_open:
            return True
        self._rest.update(REPORT_REQUESTS_TABLE, {"id": f"eq.{request['id']}"}, {
            "status": "failed", "error_class": "JobClosed", "error_message": CLOSED_JOB_MESSAGE, **_LEASE_RELEASE,
        })
        return False

    def _jobs_of(self, tick: _Tick, report_requests: list[dict]) -> dict[int, SyncJob]:
        job_ids = {int(request["job_id"]) for request in report_requests}
        missing_ids = sorted(job_ids - tick.jobs.keys())
        if missing_ids:
            for row in self._rest.select(JOBS_TABLE, {"select": "*", "id": _in_filter(missing_ids)}):
                job = SyncJob.from_row(row)
                tick.jobs[job.id] = job
        return {job_id: tick.jobs[job_id] for job_id in job_ids if job_id in tick.jobs}

    def _claim_requests(self, statuses: tuple[str, ...], limit: int,
                        kind: report_kinds.ReportKind) -> list[dict]:
        rows = self._rest.rpc("claim_report_requests", {
            "p_holder": self._holder, "p_statuses": list(statuses), "p_kinds": [kind.name],
            "p_limit": limit, "p_lease_seconds": LEASE_SECONDS,
        })
        return list(rows or [])

    def _release_requests(self, report_requests: list[dict]) -> None:
        if report_requests:
            self._rest.update(REPORT_REQUESTS_TABLE, {"id": _in_filter(_request_ids(report_requests))}, _LEASE_RELEASE)

    def _renew_job_lease(self, tick: _Tick, job: SyncJob, phase: str | None = None) -> None:
        """Every touch of a running job renews its lease, so only a job nobody works on can be claimed again."""
        current = tick.jobs.get(job.id, job)
        if current.status != "running":
            return
        lease_expires_at = self._clock() + timedelta(seconds=LEASE_SECONDS)
        changes: dict = {"lease_holder": self._holder, "lease_expires_at": lease_expires_at.isoformat()}
        if phase is not None:
            changes["phase"] = phase
        self._rest.update(JOBS_TABLE, {"id": f"eq.{job.id}", "status": "eq.running"}, changes)
        tick.jobs[job.id] = replace(current, phase=current.phase if phase is None else phase,
                                    lease_holder=self._holder, lease_expires_at=lease_expires_at)

    def _renew_job_lease_quietly(self, tick: _Tick, job: SyncJob, phase: str | None = None) -> None:
        """After a chunk was requested or saved: that progress stands even if this write fails."""
        try:
            self._renew_job_lease(tick, job, phase)
        except Exception as exc:
            self._record_error(tick, f"job {job.id} lease", exc)

    def _complete(self, tick: _Tick, job: SyncJob, *, rows_written: int, warning: str = "") -> None:
        self._jobs.complete(job, rows_written=rows_written, warning=warning, now=tick.now)
        tick.jobs[job.id] = replace(job, status="completed", phase="")
        tick.summary.jobs_completed += 1

    def _update_profile(self, tick: _Tick, profile_id: str, changes: dict) -> None:
        self._rest.update(PROFILE_SYNC_TABLE, {"profile_id": f"eq.{profile_id}"}, changes)
        tick.profiles.setdefault(profile_id, {}).update(changes)

    def _update_profile_quietly(self, tick: _Tick, profile_id: str, changes: dict) -> None:
        """For error paths: the job's own failure is already recorded, so a failed profile write only adds a note."""
        try:
            self._update_profile(tick, profile_id, changes)
        except Exception as exc:
            self._record_error(tick, f"profile {profile_id}", exc)

    def _local_today(self, tick: _Tick, profile_id: str, region: str) -> date:
        profile = tick.profiles.get(profile_id) or {}
        zone = profile_timezone(profile.get("timezone") or "", profile.get("region") or region)
        return tick.now.astimezone(zone).date()

    def _earliest_retained_day(self, tick: _Tick, job: SyncJob) -> date:
        return self._local_today(tick, job.external_account_id, job.region) - timedelta(days=_retention_days(job))

    def _waited_too_long(self, tick: _Tick, request: dict) -> bool:
        requested_at = parse_timestamp(request.get("requested_at"))
        return requested_at is not None and tick.now - requested_at > REPORT_MAX_WAIT

    def _amazon(self, job: SyncJob) -> tuple[AdsApiClient, ReportFetcher]:
        if job.connection_id is None:
            raise ConnectionUnavailable(f"job {job.id} has no amazon_ads connection")
        kind = report_kinds.by_job_kind(job.job_kind) or report_kinds.SEARCH_TERMS
        key = (job.region, job.connection_id, kind.name)
        clients = self._amazon_clients.get(key)
        if clients is None:
            api = self._api_factory(job.region, job.connection_id)
            clients = (api, kind.fetcher(api, session=self._download_session, spec=kind.spec))
            self._amazon_clients[key] = clients
        return clients

    def _token_backed_api(self, region: str, connection_id: int) -> AdsApiClient:
        return AdsApiClient(region=region, client_id_source=self._tokens.client_id,
                            token_source=self._tokens.token_source(connection_id))

    def _record_error(self, tick: _Tick, where: str, exc: Exception) -> None:
        error_class, message = sanitize_error(exc)
        tick.summary.errors.append(f"{where}: {error_class}: {message}")
        log.error("amazon_ads: %s failed: %s: %s", where, error_class, message)


def _discovered_profiles(accounts: list[dict], connection_states: dict[int, str]) -> dict[str, dict]:
    discovered: dict[str, dict] = {}
    for account in accounts:
        connection_id = _optional_int(account.get("connection_id"))
        connection_state = connection_states.get(connection_id, "") if connection_id is not None else ""
        status = _PROFILE_STATUS_BY_CONNECTION.get(connection_state, PROFILE_INACTIVE)
        for profile in account.get("profiles") or ():
            profile_id = str((profile or {}).get("profile_id") or "").strip()
            if not profile_id:
                continue
            discovered[profile_id] = {
                "profile_id": profile_id,
                "account_id": _optional_int(account.get("id")),
                "connection_id": connection_id,
                "cliente": account.get("cliente") or "",
                "account_name": account.get("nombre_externo") or "",
                "account_type": account.get("tipo") or "",
                "region": account.get("region") or "",
                "country_code": profile.get("country_code") or "",
                "currency_code": profile.get("currency_code") or "",
                "timezone": profile.get("timezone") or "",
                "access": profile.get("access") or "",
                "status": status,
            }
    return discovered


def _profile_changed(existing: dict | None, discovered: dict) -> bool:
    return existing is None or any(existing.get(column) != value for column, value in discovered.items())


def _profile_state(row: dict, job_rows: Iterable[dict], now: datetime,
                   product_histories: frozenset[str] = frozenset(), *, has_legacy_sb: bool = False) -> ProfileState:
    local_today = now.astimezone(profile_timezone(row.get("timezone") or "", row.get("region") or "")).date()
    has_open_backfill = has_day_job_today = has_portfolio_job_today = False
    has_campaign_job_today = has_campaign_entities_job_today = False
    product_today: set[str] = set()
    product_open: set[str] = set()
    entity_rows_today: dict[str, int] = {}
    for job in job_rows:
        is_open = job.get("status") in OPEN_STATUSES
        is_today = parse_date(job.get("local_day")) == local_today
        # A closed job still holding today's dedupe key would make planning again a no-op; a released key does not.
        blocks_today = is_today and (is_open or bool(job.get("dedupe_key")))
        if job.get("job_kind") in PRODUCT_KINDS:
            kind = job["job_kind"]
            completed = job.get("status") == "completed"
            product_open.update([kind] if is_open else [])
            # A completed history releases its dedupe key; it still counts as today's job, or the same day
            # would ask the last 14 days right after loading all of them.
            if blocks_today or (is_today and completed):
                product_today.add(kind)
            if is_today and completed and kind in (SP_TARGETS_KIND, SB_ENTITIES_KIND, SD_ENTITIES_KIND):
                entity_rows_today[kind] = max(entity_rows_today.get(kind, 0), int(job.get("rows_written") or 0))
            continue
        if job.get("job_kind") == PORTFOLIOS_KIND:
            has_portfolio_job_today = has_portfolio_job_today or blocks_today
        elif job.get("job_kind") == CAMPAIGNS_KIND:
            has_campaign_job_today = has_campaign_job_today or blocks_today
        elif job.get("job_kind") == CAMPAIGN_ENTITIES_KIND:
            has_campaign_entities_job_today = has_campaign_entities_job_today or blocks_today
        elif job.get("job_kind") != SEARCH_TERMS_KIND:
            continue
        elif is_backfill(job.get("trigger") or "", parse_date(job.get("window_start")), parse_date(job.get("window_end"))):
            has_open_backfill = has_open_backfill or is_open
        elif blocks_today:
            has_day_job_today = True
    return ProfileState.from_row(row, has_open_backfill=has_open_backfill, has_open_day_job_today=has_day_job_today,
                                 has_portfolio_job_today=has_portfolio_job_today,
                                 has_campaign_job_today=has_campaign_job_today,
                                 has_campaign_entities_job_today=has_campaign_entities_job_today,
                                 product_kinds_today=frozenset(product_today),
                                 product_kinds_open=frozenset(product_open),
                                 product_histories_done=product_histories,
                                 entity_rows_today=entity_rows_today, has_legacy_sb=has_legacy_sb)


def _retention_days(job: SyncJob) -> int:
    """How far back Amazon keeps the job's report: per ad product, 60 days for Sponsored Brands."""
    kind = report_kinds.by_job_kind(job.job_kind)
    return kind.spec.retention_days if kind is not None else RETENTION_DAYS


def _capped(kind_limit: int | None, worker_limit: int) -> int:
    """A report kind may ask for less than the worker allows, never more."""
    return min(kind_limit or worker_limit, worker_limit)


def _classify(exc: Exception) -> tuple[str, bool]:
    """(error_class, retryable)."""
    if isinstance(exc, oauth.NeedsReauth):
        return "NeedsReauth", False
    if isinstance(exc, ConnectionUnavailable):
        return "ConnectionUnavailable", False
    if isinstance(exc, AdsAccessDenied):
        return "AccessDenied", False
    if isinstance(exc, InvalidSyncJob):
        return "InvalidSyncJob", False
    if isinstance(exc, SaveCrashed):
        return "SaveCrashed", False
    return type(exc).__name__, True


def _empty_days_warning(empty_days: list[str]) -> str:
    if not empty_days:
        return ""
    listed = ", ".join(empty_days[:MAX_LISTED_EMPTY_DAYS])
    more = len(empty_days) - MAX_LISTED_EMPTY_DAYS
    suffix = f" y {more} más" if more > 0 else ""
    return f"día vacío: Amazon no devolvió términos para {listed}{suffix}; se conservaron los datos ya guardados"


def _discard_raw(stored_path: Path) -> None:
    try:
        stored_path.unlink(missing_ok=True)
    except OSError as exc:
        log.error("amazon_ads: could not remove the raw report of a failed save (%s)", exc)


def _request_ids(report_requests: list[dict]) -> list[int]:
    return [int(request["id"]) for request in report_requests]


def _is_missing_table(exc: Exception) -> bool:
    return (isinstance(exc, requests.HTTPError) and exc.response is not None
            and exc.response.status_code == 404)


def _optional_int(raw) -> int | None:
    return int(raw) if raw is not None else None

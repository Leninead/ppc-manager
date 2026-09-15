"""Search Term Report analyses: which ones to generate when API data arrives, and how one job runs.

Planning is level-triggered: every tick compares each account's data version and saved parameters with the
last one it planned, and only then reads the report. A data version whose payload already has an analysis
(or a job generating it) costs nothing.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ai import client
from ai.agent_call import build_agent_call
from core.ai_analysis.store import (
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    AiAnalysisStore,
    AnalysisSettings,
    NewAnalysis,
    analysis_job_kind,
)
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, ReportReadError
from core.amazon_ads.sync_planner import PROFILE_ACTIVE, SEARCH_TERMS_KIND
from core.integrations.amazon_identity import SLUG
from core.integrations.store import StoreError
from core.integrations.sync_jobs import NewSyncJob, SyncJob, SyncJobStore, sanitize_error
from core.search_term_analysis import (
    ANALYSIS_MODULE,
    CANONICAL_LANG,
    StrAnalysisParams,
    add_metric_columns,
    build_analysis_input,
    canonical_analysis_window,
    detect_columns,
)

log = logging.getLogger(__name__)

JOB_KIND = analysis_job_kind(ANALYSIS_MODULE)
SCHEDULED_MAX_ATTEMPTS = 4
SCHEDULED_DEADLINE = timedelta(hours=12)
PROVIDER_GRACE_SECONDS = 300
# Nobody waits on a scheduled analysis, so it waits as long as the provider allows (REQUEST_TIMEOUT_S).
BACKGROUND_TIMEOUT_SECONDS = 3600
# Listening a bit past the provider's limit lets its own timeout answer arrive instead of a dropped connection.
PROVIDER_RESPONSE_MARGIN_SECONDS = 60
REUSED_WARNING = "Ya había un análisis de estos mismos datos."
SUPERSEDED_WARNING = "Los parámetros de la cuenta cambiaron antes de generarlo: no se generó."
DATA_CHANGED_ERROR = ("Los datos de la cuenta cambiaron desde que se pidió el análisis. Cargá los datos nuevos en "
                      "el Search Term Report y pedilo de nuevo.")
FAILED_BEFORE_NOTE = "el análisis de estos datos ya falló o se canceló; se reintenta desde el Registro de solicitudes"
_DEFAULT_TIMEZONE = "America/Los_Angeles"


class AnalysisJobError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class PlanSummary:
    profiles_checked: int = 0
    analyses_queued: int = 0
    already_covered: int = 0
    nothing_to_analyze: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JobOutcome:
    job_id: int
    analysis_id: int | None
    reused: bool


class StrAnalysisJob:
    def __init__(self, *, store: AiAnalysisStore, jobs: SyncJobStore, reports: ReportProvider,
                 ask: Callable[..., dict] = client.ask, clock: Callable[[], datetime],
                 monotonic: Callable[[], float] = time.monotonic):
        self._store = store
        self._jobs = jobs
        self._reports = reports
        self._ask = ask
        self._clock = clock
        self._monotonic = monotonic
        # profile_id -> the (data version, settings version) last planned, so an unchanged account is not re-read.
        self._planned: dict[str, tuple] = {}

    # ── planning ─────────────────────────────────────────────────────────────

    def plan(self, profile_ids: frozenset[str] | None = None) -> PlanSummary:
        summary = PlanSummary()
        settings = self._store.settings_by_subject(ANALYSIS_MODULE)
        for profile in self._reports.profiles():
            if profile.status != PROFILE_ACTIVE or profile.data_through is None:
                continue
            if profile_ids is not None and profile.profile_id not in profile_ids:
                continue
            summary.profiles_checked += 1
            account_settings = settings.get(profile.profile_id)
            try:
                self._plan_profile(profile, account_settings, summary)
            except (ReportReadError, StoreError, OSError, ValueError) as exc:
                log.warning("ai analysis: could not plan profile %s: %s", profile.profile_id, exc)
                summary.errors.append(f"{profile.profile_id}: {exc}")
            except Exception as exc:  # a broken payload must not stop the other accounts
                log.exception("ai analysis: planning profile %s crashed", profile.profile_id)
                summary.errors.append(f"{profile.profile_id}: {type(exc).__name__}: {exc}")
                # Retried when its data or parameters change, not on every tick.
                self._planned[profile.profile_id] = _plan_version(profile, account_settings)
        return summary

    def _plan_profile(self, profile: ProfileOption, settings: AnalysisSettings | None, summary: PlanSummary) -> None:
        version = _plan_version(profile, settings)
        if self._planned.get(profile.profile_id) == version:
            return
        # Days being rewritten right now would give a payload the next tick replaces.
        if self._jobs.has_open(SLUG, SEARCH_TERMS_KIND, profile.profile_id):
            return
        params = _account_params(profile, settings)
        window_start, window_end = canonical_analysis_window(profile.data_from, profile.data_through)
        prepared = self._prepare(profile, params, window_start, window_end, CANONICAL_LANG)
        if prepared is None:
            summary.nothing_to_analyze += 1
            self._planned[profile.profile_id] = version
            return
        _, call = prepared
        if (self._store.has_analysis_for_input(ANALYSIS_MODULE, profile.profile_id, call.input_digest)
                or self._store.has_open_job(ANALYSIS_MODULE, profile.profile_id, call.input_digest)):
            summary.already_covered += 1
            self._planned[profile.profile_id] = version
            return

        now = self._clock()
        queued = self._jobs.enqueue(NewSyncJob(
            integration_slug=SLUG, job_kind=JOB_KIND, trigger="scheduled_daily",
            external_account_id=profile.profile_id, account_id=profile.account_id, connection_id=None,
            cliente=profile.cliente, account_name=profile.account_name, marketplace=profile.country_code,
            region="", window_start=window_start, window_end=window_end, local_day=_profile_today(profile, now),
            deadline_at=now + SCHEDULED_DEADLINE, max_attempts=SCHEDULED_MAX_ATTEMPTS,
            dedupe_key=f"{JOB_KIND}:{profile.profile_id}:{call.input_digest}",
            params={"module": ANALYSIS_MODULE, "lang": CANONICAL_LANG, "params": params.as_dict(),
                    "input_digest": call.input_digest},
        ))
        if queued:
            summary.analyses_queued += 1
        else:
            # No analysis and no open job, so the job holding this dedupe key ended failed or cancelled.
            summary.errors.append(f"{profile.profile_id}: {FAILED_BEFORE_NOTE}")
        self._planned[profile.profile_id] = version

    # ── one job ──────────────────────────────────────────────────────────────

    def execute(self, job: SyncJob) -> JobOutcome:
        """Runs a claimed job to completion or records the failed attempt; never raises for a job problem."""
        analysis_id = None
        try:
            profile = self._profile(job.external_account_id)
            params = StrAnalysisParams.from_dict(job.params.get("params") or {}, profile.currency_code)
            lang = job.params.get("lang") or CANONICAL_LANG
            if job.window_start is None or job.window_end is None:
                raise AnalysisJobError("El pedido no tiene período.", retryable=False)
            if job.trigger == "scheduled_daily" and params != _account_params(
                    profile, self._store.settings(ANALYSIS_MODULE, profile.profile_id)):
                self._jobs.complete(job, rows_written=0, warning=SUPERSEDED_WARNING, now=self._clock())
                return JobOutcome(job.id, None, reused=False)
            prepared = self._prepare(profile, params, job.window_start, job.window_end, lang)
            if prepared is None:
                raise AnalysisJobError("Con estos datos y parámetros no hay candidatos que analizar.",
                                       retryable=False)
            analysis_input, call = prepared
            # The page looks the analysis up by what the AM saw; one stored under newer data would never show.
            requested_digest = job.params.get("input_digest")
            if job.trigger != "scheduled_daily" and requested_digest and requested_digest != call.input_digest:
                raise AnalysisJobError(DATA_CHANGED_ERROR, retryable=False)
            if self._store.done_for_input(ANALYSIS_MODULE, profile.profile_id, call.input_digest) is not None:
                self._jobs.complete(job, rows_written=0, warning=REUSED_WARNING, now=self._clock())
                return JobOutcome(job.id, None, reused=True)

            analysis_id = self._store.start(NewAnalysis(
                module=ANALYSIS_MODULE, subject_id=profile.profile_id, window_start=job.window_start,
                window_end=job.window_end, lang=lang, params=params.as_dict(), params_digest=params.digest,
                input_digest=call.input_digest, agent_version=call.agent_version,
                trigger=TRIGGER_SCHEDULED if job.trigger == "scheduled_daily" else TRIGGER_MANUAL,
                requested_by=job.requested_by, job_id=job.id, source_last_success_at=profile.last_success_at,
                negative_records=analysis_input.negative_records, harvest_records=analysis_input.harvest_records,
                model=call.model,
            ))
            provider_call = {**call.call, "timeout_s": max(call.call["timeout_s"], BACKGROUND_TIMEOUT_SECONDS)
                             + PROVIDER_RESPONSE_MARGIN_SECONDS}
            self._jobs.set_phase(job.id, "waiting",
                                 extend_lease_seconds=provider_call["timeout_s"] + PROVIDER_GRACE_SECONDS)
            started = self._monotonic()
            response = self._ask(**provider_call)
            result = response.get("structured_output")
            if result is None:
                raise AnalysisJobError("La IA no devolvió el formato pactado.", retryable=True)
            now = self._clock()
            self._store.finish(analysis_id, result=result, response=response,
                               duration_ms=int((self._monotonic() - started) * 1000), now=now)
            self._jobs.complete(job, rows_written=len(analysis_input.negative_records)
                                + len(analysis_input.harvest_records), now=now)
            return JobOutcome(job.id, analysis_id, reused=False)
        except client.QuotaExceeded as exc:
            self._record_failure(job, analysis_id, "quota_exceeded", str(exc), retryable=True)
        except client.AIError as exc:
            self._record_failure(job, analysis_id, type(exc).__name__, str(exc), retryable=True)
        except AnalysisJobError as exc:
            self._record_failure(job, analysis_id, "analysis", str(exc), retryable=exc.retryable)
        except (ReportReadError, StoreError, OSError) as exc:
            self._record_failure(job, analysis_id, type(exc).__name__, str(exc), retryable=True)
        except Exception as exc:  # a job must never take the worker thread down silently
            log.exception("ai analysis job %s crashed", job.id)
            self._record_failure(job, analysis_id, type(exc).__name__, str(exc), retryable=True)
        return JobOutcome(job.id, analysis_id, reused=False)

    def _prepare(self, profile: ProfileOption, params: StrAnalysisParams, window_start: date, window_end: date,
                 lang: str):
        source = self._reports.search_terms(profile, window_start, window_end)
        frame = source.frame
        if frame.empty:
            return None
        cols = detect_columns(frame)
        add_metric_columns(frame, cols)
        analysis_input = build_analysis_input(frame, cols, params, currency_code=source.currency_code, lang=lang)
        if analysis_input.data is None:
            return None
        return analysis_input, build_agent_call(ANALYSIS_MODULE, analysis_input.data)

    def _profile(self, profile_id: str) -> ProfileOption:
        for profile in self._reports.profiles():
            if profile.profile_id == profile_id:
                if profile.status != PROFILE_ACTIVE or profile.data_through is None:
                    raise AnalysisJobError("La cuenta ya no está activa o todavía no tiene datos.", retryable=False)
                return profile
        raise AnalysisJobError("La cuenta ya no está sincronizada.", retryable=False)

    def _record_failure(self, job: SyncJob, analysis_id: int | None, error_class: str, message: str, *,
                        retryable: bool) -> None:
        now = self._clock()
        # The Registro and M2 show this message: no query strings or tokens.
        message = sanitize_error(RuntimeError(message))[1]
        try:
            if analysis_id is not None:
                self._store.fail(analysis_id, message=message, now=now)
            self._jobs.record_attempt_failure(job, error_class=error_class, message=message, retryable=retryable,
                                              now=now)
        except Exception:
            log.exception("ai analysis job %s: the failure could not be recorded", job.id)


def _account_params(profile: ProfileOption, settings: AnalysisSettings | None) -> StrAnalysisParams:
    return (StrAnalysisParams.from_dict(settings.params, profile.currency_code) if settings
            else StrAnalysisParams.defaults(profile.currency_code))


def _plan_version(profile: ProfileOption, settings: AnalysisSettings | None) -> tuple:
    return (profile.last_success_at, profile.data_from, profile.data_through,
            settings.updated_at if settings else None)


def _profile_today(profile: ProfileOption, now: datetime) -> date:
    return now.astimezone(ZoneInfo(profile.timezone or _DEFAULT_TIMEZONE)).date()

"""El esqueleto que comparten los análisis guardados de todos los módulos.

Planificar, encolar, ejecutar contra el provider, guardar y registrar la falla es lo mismo para
cualquier módulo: lo único propio de cada uno es de qué ventana parte, qué parámetros tiene la
cuenta y cómo arma el payload que lee su agente. Eso viaja en un `AnalysisSpec`; el resto vive acá
una sola vez, porque un bug en el manejo de fallas duplicado por módulo es un bug por módulo.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ai import client
from core.ai_analysis.store import (
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    AiAnalysisStore,
    AnalysisSettings,
    NewAnalysis,
)
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, ReportReadError
from core.amazon_ads.sync_planner import PROFILE_ACTIVE, SEARCH_TERMS_KIND
from core.integrations.amazon_identity import SLUG
from core.integrations.store import StoreError
from core.integrations.sync_jobs import NewSyncJob, SyncJob, SyncJobStore, sanitize_error

log = logging.getLogger(__name__)

SCHEDULED_MAX_ATTEMPTS = 4
SCHEDULED_DEADLINE = timedelta(hours=12)
PROVIDER_GRACE_SECONDS = 300
# Nobody waits on a scheduled analysis, so it waits as long as the provider allows (REQUEST_TIMEOUT_S).
BACKGROUND_TIMEOUT_SECONDS = 3600
# Listening a bit past the provider's limit lets its own timeout answer arrive instead of a dropped connection.
PROVIDER_RESPONSE_MARGIN_SECONDS = 60
REUSED_WARNING = "Ya había un análisis de estos mismos datos."
SUPERSEDED_WARNING = "Los parámetros de la cuenta cambiaron antes de generarlo: no se generó."
FAILED_BEFORE_NOTE = "el análisis de estos datos ya falló o se canceló; se reintenta desde el Registro de solicitudes"
SCHEDULED_TRIGGER = "scheduled_daily"
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


@dataclass(frozen=True)
class PreparedAnalysis:
    """Lo que el módulo arma para una cuenta y una ventana: la llamada al agente y sus filas."""

    call: object            # ai.agent_call.AgentCall
    record_columns: dict    # columnas de filas de ai_analyses que llena este módulo
    rows_written: int       # cuántas filas viajaron, para el registro de solicitudes


class AnalysisRunner:
    """Planifica y ejecuta los análisis guardados de UN módulo, definido por su `spec`."""

    def __init__(self, spec, *, store: AiAnalysisStore, jobs: SyncJobStore, reports: ReportProvider,
                 ask: Callable[..., dict] = client.ask, clock: Callable[[], datetime],
                 monotonic: Callable[[], float] = time.monotonic):
        self._spec = spec
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
        settings = self._store.settings_by_subject(self._spec.module)
        for profile in self._reports.profiles():
            if profile.status != PROFILE_ACTIVE:
                continue
            if profile_ids is not None and profile.profile_id not in profile_ids:
                continue
            try:
                profile = self._view(profile)
            except (ReportReadError, StoreError, OSError, ValueError) as exc:
                log.warning("ai analysis (%s): could not read the sync of profile %s: %s",
                            self._spec.module, profile.profile_id, exc)
                summary.errors.append(f"{profile.profile_id}: {exc}")
                continue
            if profile.data_through is None:
                continue
            summary.profiles_checked += 1
            account_settings = settings.get(profile.profile_id)
            try:
                self._plan_profile(profile, account_settings, summary)
            except (ReportReadError, StoreError, OSError, ValueError) as exc:
                log.warning("ai analysis (%s): could not plan profile %s: %s",
                            self._spec.module, profile.profile_id, exc)
                summary.errors.append(f"{profile.profile_id}: {exc}")
            except Exception as exc:  # a broken payload must not stop the other accounts
                log.exception("ai analysis (%s): planning profile %s crashed", self._spec.module, profile.profile_id)
                summary.errors.append(f"{profile.profile_id}: {type(exc).__name__}: {exc}")
                # Retried when its data or parameters change, not on every tick.
                self._planned[profile.profile_id] = _plan_version(profile, account_settings)
        return summary

    def _plan_profile(self, profile: ProfileOption, settings: AnalysisSettings | None, summary: PlanSummary) -> None:
        version = _plan_version(profile, settings)
        if self._planned.get(profile.profile_id) == version:
            return
        # Days being rewritten right now would give a payload the next tick replaces.
        if self._jobs.has_open(SLUG, getattr(self._spec, "source_job_kind", SEARCH_TERMS_KIND), profile.profile_id):
            return
        params = self._spec.account_params(profile, settings)
        window_start, window_end = self._spec.canonical_window(profile)
        prepared = self._spec.prepare(self._reports, profile, params, window_start, window_end, self._spec.lang)
        if prepared is None:
            summary.nothing_to_analyze += 1
            self._planned[profile.profile_id] = version
            return
        digest = prepared.call.input_digest
        if (self._store.has_analysis_for_input(self._spec.module, profile.profile_id, digest)
                or self._store.has_open_job(self._spec.module, profile.profile_id, digest)):
            summary.already_covered += 1
            self._planned[profile.profile_id] = version
            return

        now = self._clock()
        queued = self._jobs.enqueue(NewSyncJob(
            integration_slug=SLUG, job_kind=self._spec.job_kind, trigger=SCHEDULED_TRIGGER,
            external_account_id=profile.profile_id, account_id=profile.account_id, connection_id=None,
            cliente=profile.cliente, account_name=profile.account_name, marketplace=profile.country_code,
            region="", window_start=window_start, window_end=window_end, local_day=_profile_today(profile, now),
            deadline_at=now + SCHEDULED_DEADLINE, max_attempts=SCHEDULED_MAX_ATTEMPTS,
            dedupe_key=f"{self._spec.job_kind}:{profile.profile_id}:{digest}",
            params={"module": self._spec.module, "lang": self._spec.lang, "params": params.as_dict(),
                    "input_digest": digest},
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
            params = self._spec.params_from_dict(job.params.get("params") or {}, profile.currency_code)
            lang = job.params.get("lang") or self._spec.lang
            if job.window_start is None or job.window_end is None:
                raise AnalysisJobError("El pedido no tiene período.", retryable=False)
            if job.trigger == SCHEDULED_TRIGGER and params != self._spec.account_params(
                    profile, self._store.settings(self._spec.module, profile.profile_id)):
                self._jobs.complete(job, rows_written=0, warning=SUPERSEDED_WARNING, now=self._clock())
                return JobOutcome(job.id, None, reused=False)
            prepared = self._spec.prepare(self._reports, profile, params, job.window_start, job.window_end, lang)
            if prepared is None:
                raise AnalysisJobError(self._spec.nothing_to_analyze_message, retryable=False)
            call = prepared.call
            # The page looks the analysis up by what the AM saw; one stored under newer data would never show.
            requested_digest = job.params.get("input_digest")
            if job.trigger != SCHEDULED_TRIGGER and requested_digest and requested_digest != call.input_digest:
                raise AnalysisJobError(self._spec.data_changed_message, retryable=False)
            if self._store.done_for_input(self._spec.module, profile.profile_id, call.input_digest) is not None:
                self._jobs.complete(job, rows_written=0, warning=REUSED_WARNING, now=self._clock())
                return JobOutcome(job.id, None, reused=True)

            analysis_id = self._store.start(NewAnalysis(
                module=self._spec.module, subject_id=profile.profile_id, window_start=job.window_start,
                window_end=job.window_end, lang=lang, params=params.as_dict(), params_digest=params.digest,
                input_digest=call.input_digest, agent_version=call.agent_version,
                trigger=TRIGGER_SCHEDULED if job.trigger == SCHEDULED_TRIGGER else TRIGGER_MANUAL,
                requested_by=job.requested_by, job_id=job.id, source_last_success_at=profile.last_success_at,
                model=call.model,
                **{"negative_records": [], "harvest_records": [], "records": [], **prepared.record_columns},
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
            self._jobs.complete(job, rows_written=prepared.rows_written, now=now)
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

    def _view(self, profile: ProfileOption) -> ProfileOption:
        """The profile as the module's own sync sees it.

        `ads_profile_sync` is the search-term sync's; a module fed by another grain (campaigns) gives a
        `data_view(profile, jobs)` that reads its window, day and hour from its own sync requests.
        """
        data_view = getattr(self._spec, "data_view", None)
        return data_view(profile, self._jobs) if data_view is not None else profile

    def _profile(self, profile_id: str) -> ProfileOption:
        for profile in self._reports.profiles():
            if profile.profile_id == profile_id:
                profile = self._view(profile)
                if profile.status != PROFILE_ACTIVE or profile.data_through is None:
                    raise AnalysisJobError("La cuenta ya no está activa o todavía no tiene datos.", retryable=False)
                return profile
        raise AnalysisJobError("La cuenta ya no está sincronizada.", retryable=False)

    def _record_failure(self, job: SyncJob, analysis_id: int | None, error_class: str, message: str, *,
                        retryable: bool) -> None:
        now = self._clock()
        # The Registro and the module's tab show this message: no query strings or tokens.
        message = sanitize_error(RuntimeError(message))[1]
        try:
            if analysis_id is not None:
                self._store.fail(analysis_id, message=message, now=now)
            self._jobs.record_attempt_failure(job, error_class=error_class, message=message, retryable=retryable,
                                              now=now)
        except Exception:
            log.exception("ai analysis job %s: the failure could not be recorded", job.id)


def _plan_version(profile: ProfileOption, settings: AnalysisSettings | None) -> tuple:
    return (profile.last_success_at, profile.data_from, profile.data_through,
            settings.updated_at if settings else None)


def _profile_today(profile: ProfileOption, now: datetime) -> date:
    return now.astimezone(ZoneInfo(profile.timezone or _DEFAULT_TIMEZONE)).date()

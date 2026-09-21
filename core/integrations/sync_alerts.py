"""What in the sync pipeline needs a person: failures, stuck jobs, late data, a silent worker.

`build_alerts` is pure so every rule is testable without a database;
`load_alerts` feeds it and never raises.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.integrations import catalog, consent_expiry
from core.integrations.store import ACTIVE_STATUS, NEEDS_REAUTH, Connection, ConnectionStore, _Rest
from core.integrations.sync_jobs import JOBS_TABLE, SyncJob, parse_date, parse_timestamp

log = logging.getLogger(__name__)

ERROR = "error"
WARNING = "warning"
WORKER_SILENT_AFTER = timedelta(minutes=5)

FAILED_TODAY = "failed_today"
FIRST_LOAD_FAILED = "first_load_failed"
STUCK = "stuck"
STALE_DATA = "stale_data"
WORKER_SILENT = "worker_silent"
NEEDS_REAUTH_KIND = "needs_reauth"
CONSENT_EXPIRING = "consent_expiring"

PROFILE_SYNC_TABLE = "ads_profile_sync"
HEARTBEATS_TABLE = "integration_worker_heartbeats"
ADS_SLUG = "amazon_ads"

FAILED_LOOKBACK = timedelta(hours=24)
STUCK_LEASE_GRACE = timedelta(minutes=15)
STUCK_RUNNING_FOR = timedelta(hours=4)
DATA_PROMISE = time(9, 0)
DEFAULT_TIMEZONE = "America/Los_Angeles"

SEARCH_TERMS_KIND = "sp_search_terms"
BACKFILL_TRIGGER = "backfill"
RETRY_TRIGGER = "retry"

# A running job with no phase yet is also stuck: nothing reclaims it if the worker died.
_STUCK_PHASES = ("", "requesting", "saving")
_CLOSED_WITHOUT_DATA = ("failed", "cancelled")
_KIND_LABELS = {"sp_search_terms": "términos de búsqueda", "portfolio_names": "nombres de portfolios",
                "sp_campaigns": "métricas de campañas", "campaign_entities": "campañas",
                "sp_targets": "keywords y targets SP", "sp_product_ads": "productos anunciados SP",
                "sb_entities": "campañas y targets SB",
                "sd_entities": "campañas y targets SD", "sp_targeting": "métricas de targeting SP",
                "sb_campaigns": "métricas de campañas SB", "sb_targeting": "métricas de targeting SB",
                "sd_campaigns": "métricas de campañas SD", "sd_targeting": "métricas de targeting SD",
                "sb_legacy_campaigns": "métricas de campañas SB del formato anterior",
                "ai_str_analysis": "análisis IA de términos de búsqueda",
                "ai_bulk_campaigns_analysis": "análisis IA de campañas",
                "ai_ppc_insights_analysis": "análisis IA de PPC Insights"}
ANALYSIS_WORKER_NAME = "ai_analysis"
_PHASE_LABELS = {"": "arrancando", "requesting": "pidiendo el reporte", "saving": "guardando los datos"}


@dataclass(frozen=True)
class SyncAlert:
    kind: str
    severity: str
    integration_slug: str
    subject: str
    marketplaces: str
    detail: str
    since: datetime | None
    job_id: int | None = None
    connection_id: int | None = None


def build_alerts(*, failed_jobs: list[SyncJob], stuck_jobs: list[SyncJob], profiles: list[dict],
                 connections: list[Connection], heartbeat: dict | None,
                 now: datetime, first_load_jobs: list[SyncJob] = (),
                 open_jobs: list[SyncJob] = (), analysis_heartbeat: dict | None = None) -> list[SyncAlert]:
    """Every open problem, errors first and oldest first.

    `analysis_heartbeat` is the AI analysis worker's row; a host that never ran that worker has none and no alert.

    `failed_jobs` may also carry the completed jobs of the same window: a
    completion after a failure, for the same account and kind, clears it.
    `open_jobs` are the queued, running and retrying jobs: a newer one for the same account and kind
    is already working on the failure, so it is not reported meanwhile.
    `first_load_jobs` are the backfill jobs, and their retries, of profiles whose first load never finished.
    """
    first_load_alerts = _first_load_failed(first_load_jobs, profiles)
    reported_job_ids = {alert.job_id for alert in first_load_alerts}
    # The failed first load already speaks for every failed search-term job of that profile.
    reported_keys = {_job_key(job) for job in first_load_jobs if job.id in reported_job_ids}
    alerts = [
        *_failed_today([job for job in failed_jobs if _job_key(job) not in reported_keys], open_jobs, now),
        *first_load_alerts,
        *_stuck(stuck_jobs, now),
        *_stale_data(profiles, now),
        *_worker_silent(heartbeat, profiles, now),
        *_analysis_worker_silent(analysis_heartbeat, now),
        *_connection_alerts(connections, now),
    ]
    return sorted(alerts, key=_alert_order)


def load_alerts(rest: _Rest, now: datetime) -> tuple[list[SyncAlert], bool]:
    """(alerts, read_ok). A failed read yields no alerts and read_ok False, never an exception."""
    try:
        finished_rows = rest.select(
            JOBS_TABLE,
            {
                "select": "*",
                "status": "in.(failed,completed)",
                "finished_at": f"gte.{(now - FAILED_LOOKBACK).isoformat()}",
                "order": "finished_at.asc",
            },
        )
        open_rows = rest.select(JOBS_TABLE, {"select": "*", "status": "in.(pending,running,retrying)"})
        profiles = rest.select(PROFILE_SYNC_TABLE, {"select": "*"})
        heartbeats = {row["worker_name"]: row for row in rest.select(
            HEARTBEATS_TABLE, {"select": "*", "worker_name": f"in.({ADS_SLUG},{ANALYSIS_WORKER_NAME})"}
        )}
        connection_store = ConnectionStore(rest)
        connections = [
            connection
            for grouped in connection_store.by_integration_slug().values()
            for connection in grouped
        ]
        if connection_store.read_failed:
            return [], False
        open_jobs = [SyncJob.from_row(row) for row in open_rows]
        alerts = build_alerts(
            failed_jobs=[SyncJob.from_row(row) for row in finished_rows],
            stuck_jobs=[job for job in open_jobs if job.status == "running"],
            open_jobs=open_jobs,
            profiles=profiles,
            connections=connections,
            heartbeat=heartbeats.get(ADS_SLUG),
            analysis_heartbeat=heartbeats.get(ANALYSIS_WORKER_NAME),
            now=now,
            first_load_jobs=[SyncJob.from_row(row) for row in _first_load_rows(rest, profiles)],
        )
    except Exception as exc:
        log.warning("sync alerts: could not read the sync state (%s)", exc)
        return [], False
    return alerts, True


def _failed_today(jobs: list[SyncJob], open_jobs: list[SyncJob], now: datetime) -> list[SyncAlert]:
    cutoff = now - FAILED_LOOKBACK
    latest_completion: dict[tuple[str, str, str], datetime] = {}
    latest_failure: dict[tuple[str, str, str], SyncJob] = {}
    for job in jobs:
        if job.finished_at is None:
            continue
        key = _job_key(job)
        if job.status == "completed":
            latest_completion[key] = max(job.finished_at, latest_completion.get(key, job.finished_at))
        elif job.status == "failed" and job.finished_at >= cutoff:
            current = latest_failure.get(key)
            if current is None or (job.finished_at, job.id) > (current.finished_at, current.id):
                latest_failure[key] = job
    newest_open_id = {}
    for job in open_jobs:
        newest_open_id[_job_key(job)] = max(job.id, newest_open_id.get(_job_key(job), job.id))

    alerts = []
    for key, job in latest_failure.items():
        completed_at = latest_completion.get(key)
        # The worker stamps a whole tick with one time and closes completed jobs last, so a tie came after.
        if completed_at is not None and completed_at >= job.finished_at:
            continue
        if newest_open_id.get(key, 0) > job.id:
            continue
        attempts = "1 intento" if job.attempts == 1 else f"{job.attempts} intentos"
        alerts.append(SyncAlert(
            kind=FAILED_TODAY,
            severity=ERROR,
            integration_slug=job.integration_slug,
            subject=_job_subject(job),
            marketplaces=job.marketplace,
            detail=f"Falló la actualización de {_kind_label(job.job_kind)} después de {attempts}.",
            since=job.finished_at,
            job_id=job.id,
        ))
    return alerts


def _first_load_rows(rest: _Rest, profiles: list[dict]) -> list[dict]:
    profile_ids = sorted({profile["profile_id"] for profile in _awaiting_first_load(profiles)})
    if not profile_ids:
        return []
    return rest.select(
        JOBS_TABLE,
        {
            "select": "*",
            "integration_slug": f"eq.{ADS_SLUG}",
            "job_kind": f"eq.{SEARCH_TERMS_KIND}",
            "trigger": f"in.({BACKFILL_TRIGGER},{RETRY_TRIGGER})",
            "external_account_id": f"in.({','.join(profile_ids)})",
            "order": "id.asc",
        },
    )


def _first_load_failed(jobs: list[SyncJob], profiles: list[dict]) -> list[SyncAlert]:
    """No 24-hour cutoff: until the first load lands, no daily refresh is ever planned for the profile."""
    jobs_by_id = {job.id: job for job in jobs}
    latest_by_profile: dict[str, SyncJob] = {}
    for job in sorted(jobs, key=lambda job: job.id):
        if job.job_kind == SEARCH_TERMS_KIND and _retry_chain_root(job, jobs_by_id).trigger == BACKFILL_TRIGGER:
            latest_by_profile[job.external_account_id] = job

    alerts = []
    for profile in _awaiting_first_load(profiles):
        latest = latest_by_profile.get(profile["profile_id"])
        if latest is None or latest.status not in _CLOSED_WITHOUT_DATA:
            continue
        reason = latest.error_class or ("cancelada" if latest.status == "cancelled" else "sin detalle")
        alerts.append(SyncAlert(
            kind=FIRST_LOAD_FAILED,
            severity=ERROR,
            integration_slug=ADS_SLUG,
            subject=_profile_subject(profile),
            marketplaces=profile.get("country_code") or "",
            detail=f"La carga inicial no se completó: {reason}.",
            since=latest.finished_at,
            job_id=latest.id,
        ))
    return alerts


def _awaiting_first_load(profiles: list[dict]) -> list[dict]:
    return [profile for profile in profiles
            if profile.get("profile_id") and profile.get("status") == "active" and not profile.get("backfill_done_at")]


def _retry_chain_root(job: SyncJob, jobs_by_id: dict[int, SyncJob]) -> SyncJob:
    """A retry of a retry of a backfill still carries the first load."""
    visited = {job.id}
    while job.trigger == RETRY_TRIGGER and job.retry_of in jobs_by_id and job.retry_of not in visited:
        job = jobs_by_id[job.retry_of]
        visited.add(job.id)
    return job


def _stuck(jobs: list[SyncJob], now: datetime) -> list[SyncAlert]:
    alerts = []
    for job in jobs:
        if job.status != "running" or job.phase not in _STUCK_PHASES:
            continue
        lease_lost = job.lease_expires_at is not None and job.lease_expires_at < now - STUCK_LEASE_GRACE
        too_long = job.started_at is not None and job.started_at < now - STUCK_RUNNING_FOR
        if not (lease_lost or too_long):
            continue
        alerts.append(SyncAlert(
            kind=STUCK,
            severity=ERROR,
            integration_slug=job.integration_slug,
            subject=_job_subject(job),
            marketplaces=job.marketplace,
            detail=f"La solicitud de {_kind_label(job.job_kind)} quedó trabada "
                   f"{_PHASE_LABELS[job.phase]}.",
            since=job.started_at or job.lease_expires_at,
            job_id=job.id,
        ))
    return alerts


def _stale_data(profiles: list[dict], now: datetime) -> list[SyncAlert]:
    stale_by_subject: dict[str, list[tuple[dict, datetime, date | None]]] = {}
    for profile in profiles:
        if profile.get("status") != "active" or not profile.get("backfill_done_at"):
            continue
        local_now = now.astimezone(_profile_zone(profile))
        if local_now.time() < DATA_PROMISE:
            continue
        refreshed_on = parse_date(profile.get("refreshed_on"))
        if refreshed_on is not None and refreshed_on >= local_now.date():
            continue
        promise_missed_at = datetime.combine(local_now.date(), DATA_PROMISE, local_now.tzinfo)
        subject = _profile_subject(profile)
        stale_by_subject.setdefault(subject, []).append(
            (profile, promise_missed_at.astimezone(timezone.utc), refreshed_on)
        )

    alerts = []
    for subject, stale in stale_by_subject.items():
        countries = sorted({profile.get("country_code") or "" for profile, _, _ in stale} - {""})
        known_dates = [refreshed_on for _, _, refreshed_on in stale if refreshed_on is not None]
        detail = (
            f"Sin actualizar desde el {min(known_dates):%d/%m/%Y}."
            if known_dates else "Todavía no completó una actualización diaria."
        )
        alerts.append(SyncAlert(
            kind=STALE_DATA,
            severity=WARNING,
            integration_slug=ADS_SLUG,
            subject=subject,
            marketplaces=" ".join(countries),
            detail=detail,
            since=min(missed_at for _, missed_at, _ in stale),
        ))
    return alerts


def _worker_silent(heartbeat: dict | None, profiles: list[dict], now: datetime) -> list[SyncAlert]:
    active_profiles = [profile for profile in profiles if profile.get("status") == "active"]
    last_tick_at = parse_timestamp((heartbeat or {}).get("last_tick_at"))
    if last_tick_at is None:
        if not active_profiles:
            return []
        detail = "El sincronizador todavía no reportó actividad."
    elif now - last_tick_at > WORKER_SILENT_AFTER:
        minutes = int((now - last_tick_at).total_seconds() // 60)
        detail = f"El sincronizador no da señales desde hace {minutes} min."
    else:
        return []
    regions = sorted({profile.get("region") or "" for profile in active_profiles} - {""})
    return [SyncAlert(
        kind=WORKER_SILENT,
        severity=ERROR,
        integration_slug=ADS_SLUG,
        subject="Sincronizador de Amazon Ads",
        marketplaces=" ".join(regions),
        detail=detail,
        since=last_tick_at,
    )]


def _analysis_worker_silent(heartbeat: dict | None, now: datetime) -> list[SyncAlert]:
    last_tick_at = parse_timestamp((heartbeat or {}).get("last_tick_at"))
    if last_tick_at is None or now - last_tick_at <= WORKER_SILENT_AFTER:
        return []
    minutes = int((now - last_tick_at).total_seconds() // 60)
    return [SyncAlert(
        kind=WORKER_SILENT,
        severity=ERROR,
        integration_slug=ADS_SLUG,
        subject="Generador de análisis IA",
        marketplaces="",
        detail=f"El generador de análisis IA no da señales desde hace {minutes} min: los reportes nuevos se "
               "quedan sin análisis.",
        since=last_tick_at,
    )]


def _connection_alerts(connections: list[Connection], now: datetime) -> list[SyncAlert]:
    alerts = []
    for connection in connections:
        status = (connection.status or "").strip().lower()
        integration = catalog.by_slug(connection.slug)
        lifetime = integration.refresh_token_lifetime_days if integration else 0
        subject = f"Autorización de {connection.connected_by or connection.client}"
        if status == NEEDS_REAUTH:
            alerts.append(SyncAlert(
                kind=NEEDS_REAUTH_KIND,
                severity=ERROR,
                integration_slug=connection.slug,
                subject=subject,
                marketplaces=connection.marketplace,
                detail="La autorización dejó de funcionar: hay que volver a conectarla.",
                since=None,
                connection_id=connection.id,
            ))
        elif status == ACTIVE_STATUS and consent_expiry.is_expiring_soon(
                connection.consent_date, lifetime, today=now.date()):
            expires_on = consent_expiry.expiry_date(connection.consent_date, lifetime)
            alerts.append(SyncAlert(
                kind=CONSENT_EXPIRING,
                severity=WARNING,
                integration_slug=connection.slug,
                subject=subject,
                marketplaces=connection.marketplace,
                detail=f"El consentimiento vence el {expires_on:%d/%m/%Y}; renovalo antes.",
                since=None,
                connection_id=connection.id,
            ))
    return alerts


def _alert_order(alert: SyncAlert) -> tuple:
    since = alert.since or datetime.max.replace(tzinfo=timezone.utc)
    return (0 if alert.severity == ERROR else 1, since)


def _job_key(job: SyncJob) -> tuple[str, str, str]:
    return job.integration_slug, job.job_kind, job.external_account_id


def _job_subject(job: SyncJob) -> str:
    return job.cliente or job.account_name or job.external_account_id


def _profile_subject(profile: dict) -> str:
    return profile.get("cliente") or profile.get("account_name") or profile.get("profile_id") or ""


def _kind_label(job_kind: str) -> str:
    return _KIND_LABELS.get(job_kind, job_kind)


def _profile_zone(profile: dict) -> ZoneInfo:
    try:
        return ZoneInfo(profile.get("timezone") or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("sync alerts: unknown timezone %r for profile %s", profile.get("timezone"),
                    profile.get("profile_id"))
        return ZoneInfo(DEFAULT_TIMEZONE)

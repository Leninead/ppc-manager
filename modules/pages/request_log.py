"""Sistema → Registro de solicitudes: every data request the sync worker makes and what happened to it.

Admin-only. Jobs come from `SyncJobStore`, open problems from `sync_alerts.load_alerts`; retry and
cancel go through the migration's functions. Visual language mirrors `modules/pages/accounts.py`.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from core.amazon_ads.raw_reports import REPORT_REQUESTS_TABLE
from core.amazon_ads.report_kinds import REPORT_JOB_KINDS
from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    PORTFOLIOS_KIND,
    SB_ENTITIES_KIND,
    SD_ENTITIES_KIND,
    SP_TARGETS_KIND,
)
from core.integrations import catalog, roles
from core.integrations.notice import sync_alert_counts
from core.integrations.store import StoreError, _Rest, _rest_credentials
from core.integrations.sync_alerts import (ADS_SLUG, CONSENT_EXPIRING, ERROR, FAILED_TODAY, FIRST_LOAD_FAILED,
                                           HEARTBEATS_TABLE, NEEDS_REAUTH_KIND, PROFILE_SYNC_TABLE, SyncAlert,
                                           load_alerts)
from core.integrations.sync_jobs import JOB_STATUSES, OPEN_STATUSES, SyncJob, SyncJobStore, parse_timestamp
from core.ui import i18n, palette

log = logging.getLogger(__name__)

ACCOUNTS_PAGE = "🔑 Cuentas conectadas"
ARGENTINA_TIMEZONE = "America/Argentina/Buenos_Aires"
# Argentina has kept UTC-3 without daylight saving since 2009, so a fixed offset is a faithful fallback.
_ARGENTINA_FALLBACK = timezone(timedelta(hours=-3))

PAGE_SIZE = 50
SYNC_PROVIDERS = (ADS_SLUG,)
# Daily photos of an account, with no report window: what they close with is a count, not a range.
_SNAPSHOT_COUNT_KEYS = {PORTFOLIOS_KIND: "request_log.sub.portfolios",
                        CAMPAIGN_ENTITIES_KIND: "request_log.sub.campaigns",
                        SP_TARGETS_KIND: "request_log.sub.targets",
                        # SB and SD lists close with their campaign count; their targets go along.
                        SB_ENTITIES_KIND: "request_log.sub.campaigns",
                        SD_ENTITIES_KIND: "request_log.sub.campaigns"}
OVERVIEW_WINDOW = timedelta(hours=24)
PERIOD_SPANS: dict[str, timedelta | None] = {
    "day": timedelta(hours=24),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "all": None,
}

_FLASH = "request_log_flash"
_PAGES_LOADED = "request_log_pages_loaded"
_FILTER_SIGNATURE = "request_log_filter_signature"

_PHASE_LABEL_KEYS = {
    "requesting": "request_log.status.requesting",
    "waiting": "request_log.status.waiting",
    "saving": "request_log.status.saving",
}
_HINT_SUFFIXES = {
    "NeedsReauth": "needs_reauth",
    "ConnectionUnavailable": "connection_unavailable",
    "AccessDenied": "access_denied",
    "ReportFailed": "report_failed",
    "ReportTimedOut": "report_timed_out",
    "DuplicateWithoutId": "duplicate",
    "deadline": "deadline",
    "AdsThrottled": "throttled",
    "ReportRowsError": "invalid_rows",
    "RawReportError": "invalid_rows",
    "SaveCrashed": "save_crashed",
    "InvalidSyncJob": "invalid_job",
    "AdsApiError": "amazon_api",
    "HTTPError": "network",
    "ConnectionError": "network",
    "Timeout": "network",
    "ReadTimeout": "network",
    "ConnectTimeout": "network",
}
_RETRYABLE_STATUSES = ("failed", "cancelled")
_CANCELLABLE_STATUSES = ("pending", "retrying")
_RETRY_ALERT_KINDS = (FAILED_TODAY, FIRST_LOAD_FAILED)
_COLUMN_KEYS = ("status", "account", "request", "requested", "duration", "attempts", "rows", "")

# Alert row: dot, subject + chip, detail, pill, action.
_ALERT_WEIGHTS = [0.3, 2.2, 3.2, 1.6, 1.6]
# Request row: status, account, request, requested at, duration, attempts, rows, view.
_TABLE_WEIGHTS = [1.45, 1.45, 1.9, 0.75, 0.95, 0.55, 0.7, 0.5]
_SINGLE_LINE = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"

_STYLE = (
    "<style>"
    + palette.list_shell("rl_page")
    + '.st-key-rl_page, [class*="st-key-rl_band_"] { gap: 0; }'
    + palette.provider_band("rl_band_")
    + palette.tabular_row("rl_alert_")
    + palette.tabular_row("rl_row_")
    + palette.outline_button("rl_more")
    + f"""
.st-key-rl_table_head [data-testid="stHorizontalBlock"] {{
    border-bottom: 1px solid {palette.LINE};
    padding: 0 8px 6px 8px;
}}
.st-key-rl_filters {{ margin: 6px 0 14px 0; }}
"""
    + "</style>"
)


@dataclass(frozen=True)
class ActionOutcome:
    succeeded: bool
    message: str


@dataclass(frozen=True)
class ReportProgress:
    saved: int
    total: int
    rows_saved: int


@dataclass(frozen=True)
class FilterChoice:
    provider: str
    status: str
    account: str
    period: str
    only_problems: bool


@dataclass(frozen=True)
class TimelineEntry:
    moment: datetime | None
    label: str
    text: str
    is_error: bool


@dataclass(frozen=True)
class Overview:
    counts: dict
    last_tick_at: datetime | None


def argentina_zone() -> tzinfo:
    try:
        return ZoneInfo(ARGENTINA_TIMEZONE)
    except ZoneInfoNotFoundError:
        log.warning("request log: time zone %s not installed, using a fixed UTC-3", ARGENTINA_TIMEZONE)
        return _ARGENTINA_FALLBACK


def to_argentina(moment: datetime) -> datetime:
    """A naive moment is read as UTC, which is how every timestamp of the sync tables is stored."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return aware.astimezone(argentina_zone())


def format_moment(moment: datetime | None, now: datetime) -> str:
    """Argentina clock time, prefixed with 'ayer' or the date when it is not today."""
    if moment is None:
        return "—"
    local = to_argentina(moment)
    today = to_argentina(now).date()
    clock = f"{local:%H:%M}"
    if local.date() == today:
        return clock
    if local.date() == today - timedelta(days=1):
        return i18n.t("request_log.time.yesterday", time=clock)
    return i18n.t("request_log.time.dated", day=local.day,
                  month=i18n.months_short()[local.month - 1], time=clock)


def short_date(day: date) -> str:
    return i18n.t("request_log.date.short", day=day.day, month=i18n.months_short()[day.month - 1])


def window_text(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return ""
    return i18n.tn("request_log.window", (end - start).days + 1, start=short_date(start), end=short_date(end))


def format_elapsed(seconds: float) -> str:
    total = max(int(seconds), 0)
    if total < 60:
        return f"{total} s"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def duration_text(job: SyncJob, now: datetime) -> str:
    if job.status == "retrying":
        return i18n.t("request_log.duration.waiting")
    if job.started_at is None:
        return "—"
    if job.is_open:
        return i18n.t("request_log.duration.running",
                      elapsed=format_elapsed((now - job.started_at).total_seconds()))
    if job.finished_at is None:
        return "—"
    return format_elapsed((job.finished_at - job.started_at).total_seconds())


def format_count(count: int) -> str:
    grouped = f"{count:,}"
    return grouped.replace(",", ".") if i18n.current_lang() == "es" else grouped


def status_label(status: str, phase: str = "", warning: str = "", job_kind: str = "") -> str:
    if status == "running":
        return i18n.t(_PHASE_LABEL_KEYS.get(phase, "request_log.status.running"))
    if status == "completed" and warning:
        # The only warning a report job closes with is a day Amazon returned empty.
        empty_day = job_kind in REPORT_JOB_KINDS
        return i18n.t("request_log.status.completed_empty_day" if empty_day
                      else "request_log.status.completed_warning")
    if status in JOB_STATUSES:
        return i18n.t(f"request_log.status.{status}")
    return status or "—"


def status_kind(status: str, warning: str = "") -> str:
    """The `palette.status_pill_html` kind for a job."""
    if status == "failed":
        return "err"
    if status == "retrying" or (status == "completed" and warning):
        return "warn"
    if status == "completed":
        return "ok"
    return "idle"


def attempts_shown(status: str, attempts: int) -> int:
    """`attempts` counts failures; a running or completed job is also on the attempt after them."""
    return attempts + 1 if status in ("running", "completed") else attempts


def is_abandoned(job: SyncJob, now: datetime) -> bool:
    """Running with a lapsed lease: no worker is holding it, so an admin may cancel it."""
    return job.status == "running" and (job.lease_expires_at is None or job.lease_expires_at < now)


def is_cancellable(job: SyncJob, now: datetime) -> bool:
    return job.status in _CANCELLABLE_STATUSES or is_abandoned(job, now)


def hint_key(error_class: str) -> str:
    return f"request_log.hint.{_HINT_SUFFIXES.get(error_class, 'default')}"


def verdict_title(errors: int, warnings: int, read_ok: bool) -> str:
    """Never all-clear when the alerts could not be read: silence would be a lie."""
    if not read_ok:
        return i18n.t("request_log.verdict.read_failed")
    if errors and warnings:
        return i18n.t("request_log.verdict.mixed", errors=errors, warnings=warnings,
                      error_word=i18n.tn("request_log.word_problem", errors),
                      warning_word=i18n.tn("request_log.word_warning", warnings))
    if errors:
        return i18n.tn("request_log.verdict.errors", errors)
    if warnings:
        return i18n.tn("request_log.verdict.warnings", warnings)
    return i18n.t("request_log.verdict.all_clear")


def summary_line(counts: dict, last_tick_at: datetime | None, now: datetime) -> str:
    items = []
    open_count = sum(counts.get(status, 0) for status in OPEN_STATUSES)
    for key, count in (("completed", counts.get("completed", 0)), ("open", open_count),
                       ("failed", counts.get("failed", 0)), ("cancelled", counts.get("cancelled", 0))):
        if count:
            items.append(i18n.tn(f"request_log.summary.{key}", count))
    if not items:
        items.append(i18n.t("request_log.summary.no_requests"))
    if last_tick_at is None:
        items.append(i18n.t("request_log.summary.worker_never"))
    else:
        age = format_elapsed((now - last_tick_at).total_seconds())
        items.append(i18n.t("request_log.summary.worker_seen", age=age))
    return i18n.t("request_log.summary.window", items=" · ".join(items))


def list_filters(choice: FilterChoice, now: datetime) -> dict:
    """The `SyncJobStore.list_recent` keyword arguments for what the filters say."""
    span = PERIOD_SPANS.get(choice.period)
    return {
        "slugs": (choice.provider,) if choice.provider else (),
        "statuses": (choice.status,) if choice.status else (),
        "external_account_id": choice.account,
        "since": now - span if span is not None else None,
        "only_problems": choice.only_problems,
    }


def load_job_pages(store: SyncJobStore, filters: dict, pages: int,
                   page_size: int = PAGE_SIZE) -> tuple[list[SyncJob], bool]:
    """The first `pages` keyset pages, newest first, and whether another page may follow."""
    jobs: list[SyncJob] = []
    before_id = None
    for _ in range(max(pages, 1)):
        page = store.list_recent(**filters, limit=page_size, before_id=before_id)
        jobs.extend(page)
        if len(page) < page_size:
            return jobs, False
        before_id = page[-1].id
    return jobs, True


def report_progress(report_requests: list[dict]) -> dict[int, ReportProgress]:
    tallies: dict[int, tuple[int, int, int]] = {}
    for request in report_requests:
        job_id = int(request["job_id"])
        saved, total, rows = tallies.get(job_id, (0, 0, 0))
        is_saved = request.get("status") == "saved"
        tallies[job_id] = (saved + int(is_saved), total + 1,
                           rows + (int(request.get("row_count") or 0) if is_saved else 0))
    return {job_id: ReportProgress(*tally) for job_id, tally in tallies.items()}


def account_label(job: SyncJob) -> str:
    return job.cliente or job.account_name or job.external_account_id or "—"


def request_title(job: SyncJob) -> str:
    kind = _label_or(f"request_log.kind.{job.job_kind}", job.job_kind)
    if job.job_kind in _SNAPSHOT_COUNT_KEYS:
        return kind
    trigger = _label_or(f"request_log.trigger.{job.trigger}", job.trigger)
    if job.trigger == "manual" and job.requested_by:
        return i18n.t("request_log.request_title_by", trigger=trigger, user=job.requested_by)
    return i18n.t("request_log.request_title", trigger=trigger, kind=kind)


def request_subline(job: SyncJob, progress: ReportProgress | None, now: datetime) -> str:
    if job.status == "retrying" and job.next_attempt_at is not None:
        return i18n.t("request_log.sub.next_attempt", time=format_moment(job.next_attempt_at, now))
    if job.status == "running" and progress is not None and progress.total:
        return i18n.t("request_log.sub.reports_ready", saved=progress.saved, total=progress.total)
    if job.status == "cancelled" and job.error_message:
        return job.error_message
    if job.status == "completed" and job.warning:
        return job.warning
    if job.job_kind in _SNAPSHOT_COUNT_KEYS and job.status == "completed":
        return i18n.tn(_SNAPSHOT_COUNT_KEYS[job.job_kind], job.rows_written or 0)
    return window_text(job.window_start, job.window_end)


def rows_text(job: SyncJob, progress: ReportProgress | None) -> str:
    if job.rows_written is not None:
        return format_count(job.rows_written)
    if progress is not None and progress.rows_saved:
        return format_count(progress.rows_saved)
    return "—"


def origin_text(job: SyncJob) -> str:
    user = job.requested_by or "—"
    if job.trigger == "manual":
        return i18n.t("request_log.origin.manual", user=user)
    if job.trigger == "retry":
        return i18n.t("request_log.origin.retry", job_id=job.retry_of or "—", user=user)
    return _label_or(f"request_log.origin.{job.trigger}", job.trigger)


def timeline(job: SyncJob) -> list[TimelineEntry]:
    """What happened to a job, oldest first: creation, each failed attempt, then how it closed."""
    entries = [TimelineEntry(job.created_at, i18n.t("request_log.detail.created_event"), origin_text(job), False)]
    for logged in job.attempt_log:
        cause = " · ".join(part for part in (logged.get("error_class"), logged.get("message")) if part)
        entries.append(TimelineEntry(_timestamp_or_none(logged.get("at")),
                                     i18n.t("request_log.detail.attempt", n=logged.get("attempt", "?")),
                                     cause, True))
    closing_label = status_label(job.status, job.phase, job.warning, job.job_kind)
    if job.status == "completed":
        rows = job.rows_written or 0
        saved = i18n.tn("request_log.detail.rows_saved", rows, count=format_count(rows))
        entries.append(TimelineEntry(job.finished_at, closing_label,
                                     f"{saved} {job.warning}".strip(), False))
    elif job.status in _RETRYABLE_STATUSES:
        logged_messages = {logged.get("message") for logged in job.attempt_log}
        if job.error_message and job.error_message not in logged_messages:
            cause = " · ".join(part for part in (job.error_class, job.error_message) if part)
            entries.append(TimelineEntry(job.finished_at, closing_label, cause, job.status == "failed"))
    return entries


def retry_request(store: SyncJobStore, job_id: int, actor: str, role: str) -> ActionOutcome:
    """Re-checks the role: a button already on screen is not a permission."""
    if not roles.is_admin(role):
        return ActionOutcome(False, i18n.t("request_log.admin_only"))
    try:
        new_job_id = store.retry(job_id, actor or roles.ADMIN)
    except StoreError as exc:
        return ActionOutcome(False, str(exc))
    if new_job_id is None:
        return ActionOutcome(False, i18n.t("request_log.flash.not_retryable", job_id=job_id))
    return ActionOutcome(True, i18n.t("request_log.flash.retried", job_id=job_id, new_job_id=new_job_id))


def cancel_request(store: SyncJobStore, job_id: int, actor: str, role: str) -> ActionOutcome:
    """Re-checks the role: a button already on screen is not a permission."""
    if not roles.is_admin(role):
        return ActionOutcome(False, i18n.t("request_log.admin_only"))
    try:
        cancelled = store.cancel(job_id, actor or roles.ADMIN)
    except StoreError as exc:
        return ActionOutcome(False, str(exc))
    if not cancelled:
        return ActionOutcome(False, i18n.t("request_log.flash.not_cancellable", job_id=job_id))
    return ActionOutcome(True, i18n.t("request_log.flash.cancelled", job_id=job_id))


def render(username: str = "", role: str = roles.USER) -> None:
    """Sistema → Registro de solicitudes. Admin-only."""
    if not roles.is_admin(role):
        st.info(i18n.t("request_log.admin_only"))
        return

    st.markdown(f"## {i18n.t('request_log.header_title')}")
    st.caption(i18n.t("request_log.header_caption"))
    st.divider()
    with st.expander(i18n.t("request_log.sop_expander"), expanded=False):
        st.markdown(i18n.t("request_log.sop_md"))

    rest = _open_rest()
    if rest is None:
        st.warning(i18n.t("request_log.error_db_unavailable"))
        return

    _show_flash()
    store = SyncJobStore(rest)
    now = datetime.now(timezone.utc)
    alerts, alerts_read_ok = load_alerts(rest, now)
    overview = _load_overview(rest, store, now)

    st.markdown(_STYLE, unsafe_allow_html=True)
    with st.container(key="rl_page"):
        _verdict(alerts, alerts_read_ok, overview, now)
        _attention_band(alerts, alerts_read_ok, rest, username, role)
        _requests_band(rest, store, username, role, now)


def _open_rest() -> _Rest | None:
    credentials = _rest_credentials()
    return _Rest(*credentials) if credentials is not None else None


def _show_flash() -> None:
    flash = st.session_state.pop(_FLASH, None)
    if not flash:
        return
    succeeded, message = flash
    (st.success if succeeded else st.warning)(message)


def _apply(outcome: ActionOutcome) -> None:
    st.session_state[_FLASH] = (outcome.succeeded, outcome.message)
    sync_alert_counts.clear()
    st.rerun()


def _load_overview(rest: _Rest, store: SyncJobStore, now: datetime) -> Overview | None:
    try:
        counts = store.counts_since(now - OVERVIEW_WINDOW)
        heartbeats = rest.select(
            HEARTBEATS_TABLE, {"select": "last_tick_at", "worker_name": f"eq.{ADS_SLUG}", "limit": "1"}
        )
    except Exception as exc:
        log.warning("request log: could not read the 24-hour overview (%s)", exc)
        return None
    last_tick_at = _timestamp_or_none(heartbeats[0].get("last_tick_at")) if heartbeats else None
    return Overview(counts=counts, last_tick_at=last_tick_at)


def _verdict(alerts: list[SyncAlert], read_ok: bool, overview: Overview | None, now: datetime) -> None:
    errors = sum(1 for alert in alerts if alert.severity == ERROR)
    title = verdict_title(errors, len(alerts) - errors, read_ok)
    detail = (summary_line(overview.counts, overview.last_tick_at, now) if overview is not None
              else i18n.t("request_log.summary.read_failed"))
    st.markdown(
        f"<h3 style='margin:0 0 4px 0;font-size:16px;font-weight:600;color:{palette.FG};'>"
        f"{html.escape(title)}</h3>"
        f"<p style='margin:0 0 20px 0;font-size:12.5px;color:{palette.FG_SUBTLE};'>{html.escape(detail)}</p>",
        unsafe_allow_html=True,
    )


def _attention_band(alerts: list[SyncAlert], read_ok: bool, rest: _Rest, username: str, role: str) -> None:
    """An empty band is not drawn: the verdict already says nothing needs attention."""
    if read_ok and not alerts:
        return
    count = i18n.tn("request_log.alerts.count", len(alerts)) if read_ok else ""
    with st.container(key="rl_band_alerts"):
        st.markdown(
            palette.band_header_html(title=html.escape(i18n.t("request_log.alerts.title")),
                                     tag=html.escape(i18n.t("request_log.alerts.tag")),
                                     right=_band_count_html(count)),
            unsafe_allow_html=True,
        )
        if not read_ok:
            st.markdown(palette.band_note_html(html.escape(i18n.t("request_log.alerts.read_failed"))),
                        unsafe_allow_html=True)
            return
        for index, alert in enumerate(alerts):
            _alert_row(index, alert, rest, username, role)


def _alert_row(index: int, alert: SyncAlert, rest: _Rest, username: str, role: str) -> None:
    kind = "err" if alert.severity == ERROR else "warn"
    with st.container(key=f"rl_alert_{index}"):
        cells = st.columns(_ALERT_WEIGHTS, gap="small", vertical_alignment="center")
        cells[0].markdown(_dot_html(kind), unsafe_allow_html=True)
        cells[1].markdown(_name_with_chip_html(alert.subject, alert.marketplaces), unsafe_allow_html=True)
        cells[2].markdown(_one_line_html(alert.detail), unsafe_allow_html=True)
        label = _label_or(f"request_log.alert.{alert.kind}", alert.kind)
        cells[3].markdown(palette.status_pill_html(kind, html.escape(label)), unsafe_allow_html=True)
        with cells[4]:
            _alert_action(index, alert, rest, username, role)


def _alert_action(index: int, alert: SyncAlert, rest: _Rest, username: str, role: str) -> None:
    if alert.kind in _RETRY_ALERT_KINDS and alert.job_id is not None:
        if st.button(i18n.t("request_log.btn.retry"), key=f"rl_act_retry_{alert.job_id}",
                     icon=":material/refresh:", type="tertiary"):
            _apply(retry_request(SyncJobStore(rest), alert.job_id, username, role))
    elif alert.kind in (NEEDS_REAUTH_KIND, CONSENT_EXPIRING):
        if st.button(i18n.t("request_log.btn.accounts"), key=f"rl_act_accounts_{index}",
                     icon=":material/key:", type="tertiary"):
            st.session_state["selected_page"] = ACCOUNTS_PAGE
            st.rerun()
    elif alert.job_id is not None:
        if st.button(i18n.t("request_log.btn.view"), key=f"rl_act_view_{alert.job_id}", type="tertiary"):
            _open_detail(rest, alert.job_id, username, role)


def _requests_band(rest: _Rest, store: SyncJobStore, username: str, role: str, now: datetime) -> None:
    with st.container(key="rl_band_requests"):
        header_slot = st.empty()
        choice = _filter_widgets(rest)
        if st.session_state.get(_FILTER_SIGNATURE) != choice:
            st.session_state[_FILTER_SIGNATURE] = choice
            st.session_state[_PAGES_LOADED] = 1
        pages = int(st.session_state.get(_PAGES_LOADED, 1))
        try:
            jobs, has_more = load_job_pages(store, list_filters(choice, now), pages)
        except Exception as exc:
            log.warning("request log: could not list sync jobs (%s)", exc)
            header_slot.markdown(_requests_header_html(""), unsafe_allow_html=True)
            st.warning(i18n.t("request_log.requests.read_failed"))
            return
        header_slot.markdown(_requests_header_html(i18n.tn("request_log.requests.shown", len(jobs))),
                             unsafe_allow_html=True)
        if not jobs:
            st.markdown(palette.band_note_html(html.escape(i18n.t("request_log.requests.empty"))),
                        unsafe_allow_html=True)
            return
        progress = _load_report_progress(rest, jobs)
        _table_header()
        for job in jobs:
            _job_row(job, progress.get(job.id), rest, username, role, now)
        if has_more:
            with st.container(key="rl_more"):
                if st.button(i18n.t("request_log.btn.load_more"), key="rl_load_more"):
                    st.session_state[_PAGES_LOADED] = pages + 1
                    st.rerun()


def _requests_header_html(right_text: str) -> str:
    return palette.band_header_html(title=html.escape(i18n.t("request_log.requests.title")),
                                    tag=html.escape(i18n.t("request_log.requests.tag")),
                                    right=_band_count_html(right_text))


def _filter_widgets(rest: _Rest) -> FilterChoice:
    accounts = _account_options(rest)
    with st.container(key="rl_filters"):
        cells = st.columns([1.3, 1.3, 1.3, 1.1, 1.2], gap="medium", vertical_alignment="bottom")
        provider = cells[0].selectbox(i18n.t("request_log.filter.provider"), ("",) + SYNC_PROVIDERS,
                                      format_func=_provider_option, key="rl_filter_provider")
        status = cells[1].selectbox(i18n.t("request_log.filter.status"), ("",) + JOB_STATUSES,
                                    format_func=_status_option, key="rl_filter_status")
        account = cells[2].selectbox(
            i18n.t("request_log.filter.account"), ("",) + tuple(accounts),
            format_func=lambda profile_id: accounts.get(profile_id) or i18n.t("request_log.filter.all_accounts"),
            key="rl_filter_account",
        )
        period = cells[3].selectbox(i18n.t("request_log.filter.period"), tuple(PERIOD_SPANS),
                                    format_func=lambda span: i18n.t(f"request_log.period.{span}"),
                                    key="rl_filter_period")
        only_problems = cells[4].toggle(i18n.t("request_log.filter.only_problems"), key="rl_filter_problems")
    return FilterChoice(provider=provider, status=status, account=account, period=period,
                        only_problems=only_problems)


def _provider_option(slug: str) -> str:
    if not slug:
        return i18n.t("request_log.filter.all_providers")
    integration = catalog.by_slug(slug)
    return integration.name if integration else slug


def _status_option(status: str) -> str:
    return status_label(status) if status else i18n.t("request_log.filter.all_statuses")


def _account_options(rest: _Rest) -> dict[str, str]:
    try:
        rows = rest.select(PROFILE_SYNC_TABLE, {"select": "profile_id,cliente,account_name,country_code",
                                                "order": "cliente.asc,country_code.asc"})
    except Exception as exc:
        log.warning("request log: could not read the profiles for the account filter (%s)", exc)
        return {}
    options = {}
    for row in rows:
        profile_id = row.get("profile_id") or ""
        if not profile_id:
            continue
        name = row.get("cliente") or row.get("account_name") or profile_id
        country = row.get("country_code") or ""
        options[profile_id] = f"{name} · {country}" if country else name
    return options


def _load_report_progress(rest: _Rest, jobs: list[SyncJob]) -> dict[int, ReportProgress]:
    open_ids = [job.id for job in jobs if job.is_open and job.job_kind in REPORT_JOB_KINDS]
    if not open_ids:
        return {}
    try:
        rows = rest.select(REPORT_REQUESTS_TABLE, {
            "select": "job_id,status,row_count",
            "job_id": f"in.({','.join(str(job_id) for job_id in open_ids)})",
        })
    except Exception as exc:
        log.warning("request log: could not read report progress (%s)", exc)
        return {}
    return report_progress(rows)


def _table_header() -> None:
    with st.container(key="rl_table_head"):
        cells = st.columns(_TABLE_WEIGHTS, gap="small", vertical_alignment="bottom")
        for cell, column in zip(cells, _COLUMN_KEYS):
            label = i18n.t(f"request_log.column.{column}") if column else ""
            align = "right" if column == "rows" else "left"
            cell.markdown(
                f"<div style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;"
                f"color:{palette.FG_SUBTLE};text-align:{align};'>{html.escape(label)}</div>",
                unsafe_allow_html=True,
            )


def _job_row(job: SyncJob, progress: ReportProgress | None, rest: _Rest, username: str, role: str,
             now: datetime) -> None:
    with st.container(key=f"rl_row_{job.id}"):
        cells = st.columns(_TABLE_WEIGHTS, gap="small", vertical_alignment="center")
        label = status_label(job.status, job.phase, job.warning, job.job_kind)
        cells[0].markdown(palette.status_pill_html(status_kind(job.status, job.warning), html.escape(label)),
                          unsafe_allow_html=True)
        cells[1].markdown(_name_with_chip_html(account_label(job), job.marketplace), unsafe_allow_html=True)
        cells[2].markdown(_two_line_html(request_title(job), request_subline(job, progress, now)),
                          unsafe_allow_html=True)
        cells[3].markdown(_cell_html(format_moment(job.created_at, now)), unsafe_allow_html=True)
        cells[4].markdown(_cell_html(duration_text(job, now)), unsafe_allow_html=True)
        cells[5].markdown(_cell_html(f"{attempts_shown(job.status, job.attempts)}/{job.max_attempts}",
                                     color=_attempts_color(job.status)), unsafe_allow_html=True)
        rows = rows_text(job, progress)
        cells[6].markdown(_cell_html(rows, color=palette.FG_MUTED if rows == "—" else palette.FG, align="right"),
                          unsafe_allow_html=True)
        with cells[7]:
            if st.button(i18n.t("request_log.btn.view"), key=f"rl_view_{job.id}", type="tertiary"):
                _open_detail(rest, job.id, username, role)


def _attempts_color(status: str) -> str:
    return {"failed": palette.ERR_INK, "retrying": palette.WARN_INK}.get(status, palette.FG_MUTED)


def _open_detail(rest: _Rest, job_id: int, username: str, role: str) -> None:
    """Decorated per call: `st.dialog` binds its title once, which would freeze it in one language."""
    st.dialog(i18n.t("request_log.detail.dialog_title"), width="large")(_detail_body)(
        rest, job_id, username, role
    )


def _detail_body(rest: _Rest, job_id: int, username: str, role: str) -> None:
    store = SyncJobStore(rest)
    now = datetime.now(timezone.utc)
    try:
        job = store.get(job_id)
    except Exception as exc:
        log.warning("request log: could not read sync job %s (%s)", job_id, exc)
        st.error(i18n.t("request_log.detail.read_failed"))
        return
    if job is None:
        st.info(i18n.t("request_log.detail.not_found"))
        return

    st.markdown(_detail_heading_html(job), unsafe_allow_html=True)
    st.markdown(_facts_html(_detail_facts(job, now)), unsafe_allow_html=True)
    st.markdown(_section_label_html(i18n.t("request_log.detail.timeline")), unsafe_allow_html=True)
    st.markdown(_timeline_html(timeline(job), now), unsafe_allow_html=True)
    if job.job_kind in REPORT_JOB_KINDS:
        _report_chunks(rest, job)
    if job.error_class or job.error_message:
        st.markdown(_section_label_html(i18n.t("request_log.detail.error")), unsafe_allow_html=True)
        st.code(" · ".join(part for part in (job.error_class, job.error_message) if part),
                language=None, wrap_lines=True)
        if job.status in ("failed", "retrying"):
            st.markdown(_hint_html(i18n.t(hint_key(job.error_class))), unsafe_allow_html=True)
    elif job.warning:
        st.markdown(_section_label_html(i18n.t("request_log.detail.warning")), unsafe_allow_html=True)
        st.markdown(_hint_html(job.warning), unsafe_allow_html=True)
    _detail_actions(store, job, username, role, now)


def _detail_actions(store: SyncJobStore, job: SyncJob, username: str, role: str, now: datetime) -> None:
    st.divider()
    caption_cell, close_cell, action_cell = st.columns([3.2, 1, 1.4], vertical_alignment="center")
    if job.status in _RETRYABLE_STATUSES:
        caption_cell.caption(i18n.t("request_log.detail.retry_caption"))
        if action_cell.button(i18n.t("request_log.btn.retry_now"), key=f"rl_detail_retry_{job.id}",
                              type="primary", icon=":material/refresh:", use_container_width=True):
            _apply(retry_request(store, job.id, username, role))
    elif is_cancellable(job, now):
        caption_key = ("request_log.detail.cancel_abandoned_caption" if is_abandoned(job, now)
                       else "request_log.detail.cancel_caption")
        caption_cell.caption(i18n.t(caption_key))
        if action_cell.button(i18n.t("request_log.btn.cancel_job"), key=f"rl_detail_cancel_{job.id}",
                              icon=":material/block:", use_container_width=True):
            _apply(cancel_request(store, job.id, username, role))
    if close_cell.button(i18n.t("request_log.btn.close"), key=f"rl_detail_close_{job.id}",
                         use_container_width=True):
        st.rerun()


def _detail_facts(job: SyncJob, now: datetime) -> list[tuple[str, str]]:
    """(label, value HTML) pairs; every value from the database is escaped here."""
    closing_label, closing_moment = {
        "failed": ("request_log.detail.gave_up", job.finished_at),
        "completed": ("request_log.detail.finished", job.finished_at),
        "cancelled": ("request_log.detail.cancelled_at", job.finished_at),
        "retrying": ("request_log.detail.next_attempt", job.next_attempt_at),
    }.get(job.status, ("request_log.detail.deadline", job.deadline_at))
    rows = format_count(job.rows_written) if job.rows_written is not None else "—"
    return [
        (i18n.t("request_log.detail.account"),
         f"{html.escape(account_label(job))} {palette.marketplace_chip_html(html.escape(job.marketplace))}"),
        (i18n.t("request_log.detail.profile"),
         f"<span style='font-family:{palette.MONO_STACK};'>{html.escape(job.external_account_id or '—')}</span>"),
        (i18n.t("request_log.detail.window"), html.escape(window_text(job.window_start, job.window_end) or "—")),
        (i18n.t("request_log.detail.origin"), html.escape(origin_text(job))),
        (i18n.t("request_log.detail.created"), html.escape(format_moment(job.created_at, now))),
        (i18n.t(closing_label), html.escape(format_moment(closing_moment, now))),
        (i18n.t("request_log.detail.rows"), html.escape(rows)),
        (i18n.t("request_log.detail.attempts"),
         html.escape(f"{attempts_shown(job.status, job.attempts)}/{job.max_attempts}")),
    ]


def _report_chunks(rest: _Rest, job: SyncJob) -> None:
    st.markdown(_section_label_html(i18n.t("request_log.detail.reports")), unsafe_allow_html=True)
    try:
        chunks = rest.select(REPORT_REQUESTS_TABLE, {
            "select": "window_start,window_end,status,amazon_report_id,amazon_status,row_count",
            "job_id": f"eq.{job.id}",
            "order": "window_start.desc",
        })
    except Exception as exc:
        log.warning("request log: could not read the report requests of job %s (%s)", job.id, exc)
        st.caption(i18n.t("request_log.detail.reports_read_failed"))
        return
    if not chunks:
        st.caption(i18n.t("request_log.detail.reports_empty"))
        return
    st.markdown(_chunks_html(chunks), unsafe_allow_html=True)


def _chunks_html(chunks: list[dict]) -> str:
    grid = "display:grid;grid-template-columns:1.3fr 2.2fr 1.2fr 0.8fr;gap:12px;align-items:center;"
    head = "".join(
        f"<span style='text-align:{'right' if key == 'report_rows' else 'left'};'>"
        f"{html.escape(i18n.t(f'request_log.detail.{key}'))}</span>"
        for key in ("report_window", "report_id", "report_status", "report_rows")
    )
    lines = [
        f"<div style='{grid}padding:0 0 6px 0;font-size:11px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{palette.FG_SUBTLE};border-bottom:1px solid {palette.LINE};'>{head}</div>"
    ]
    for chunk in chunks:
        start = _date_or_none(chunk.get("window_start"))
        end = _date_or_none(chunk.get("window_end"))
        span = f"{short_date(start)} → {short_date(end)}" if start and end else "—"
        local_status = _label_or(f"request_log.chunk.{chunk.get('status') or ''}", chunk.get("status") or "—")
        amazon_status = chunk.get("amazon_status") or ""
        status_text = f"{local_status} · {amazon_status}" if amazon_status else local_status
        status_color = palette.ERR_INK if chunk.get("status") == "failed" else palette.FG
        rows = chunk.get("row_count")
        lines.append(
            f"<div style='{grid}padding:8px 0;border-bottom:1px solid {palette.LINE_SOFT};font-size:13px;"
            f"font-variant-numeric:tabular-nums;'>"
            f"<span style='color:{palette.FG};'>{html.escape(span)}</span>"
            f"<span style='font-family:{palette.MONO_STACK};color:{palette.FG};{_SINGLE_LINE}'>"
            f"{html.escape(chunk.get('amazon_report_id') or '—')}</span>"
            f"<span style='color:{status_color};'>{html.escape(status_text)}</span>"
            f"<span style='color:{palette.FG_MUTED};text-align:right;'>"
            f"{html.escape(format_count(int(rows)) if rows is not None else '—')}</span></div>"
        )
    return "".join(lines)


def _detail_heading_html(job: SyncJob) -> str:
    integration = catalog.by_slug(job.integration_slug)
    provider = integration.name if integration else job.integration_slug
    kind = _label_or(f"request_log.kind.{job.job_kind}", job.job_kind)
    eyebrow = i18n.t("request_log.detail.eyebrow", provider=provider, kind=kind, job_id=job.id)
    label = status_label(job.status, job.phase, job.warning, job.job_kind)
    return (
        f"<div style='display:flex;align-items:flex-start;justify-content:space-between;gap:16px;'>"
        f"<div style='display:flex;flex-direction:column;gap:6px;min-width:0;'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;"
        f"color:{palette.FG_SUBTLE};'>{html.escape(eyebrow)}</span>"
        f"<span style='font-size:22px;font-weight:600;color:{palette.FG};'>"
        f"{html.escape(account_label(job))} · {html.escape(request_title(job))}</span></div>"
        f"{palette.status_pill_html(status_kind(job.status, job.warning), html.escape(label))}</div>"
    )


def _facts_html(facts: list[tuple[str, str]]) -> str:
    cells = "".join(
        f"<div style='display:flex;flex-direction:column;gap:3px;min-width:0;'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;"
        f"color:{palette.FG_SUBTLE};'>{html.escape(label)}</span>"
        f"<span style='font-size:14px;color:{palette.FG};display:flex;align-items:center;gap:8px;'>{value}</span>"
        f"</div>"
        for label, value in facts
    )
    return (
        f"<div style='display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px 20px;padding:16px 0;"
        f"margin:12px 0 8px 0;border-top:1px solid {palette.LINE};border-bottom:1px solid {palette.LINE};"
        f"font-variant-numeric:tabular-nums;'>{cells}</div>"
    )


def _timeline_html(entries: list[TimelineEntry], now: datetime) -> str:
    return "".join(
        f"<div style='display:grid;grid-template-columns:100px 90px 1fr;gap:12px;align-items:baseline;"
        f"padding:8px 0;border-bottom:1px solid {palette.LINE_SOFT};font-variant-numeric:tabular-nums;'>"
        f"<span style='font-size:13px;color:{palette.FG_MUTED};'>{html.escape(format_moment(entry.moment, now))}</span>"
        f"<span style='font-size:13px;color:{palette.FG_MUTED};'>{html.escape(entry.label)}</span>"
        f"<span style='font-size:14px;color:{palette.ERR_INK if entry.is_error else palette.FG};'>"
        f"{html.escape(entry.text or '—')}</span></div>"
        for entry in entries
    )


def _section_label_html(text: str) -> str:
    return (
        f"<div style='margin:14px 0 6px 0;font-size:11px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{palette.FG_SUBTLE};'>{html.escape(text)}</div>"
    )


def _hint_html(text: str) -> str:
    return (
        f"<div style='background:{palette.ATTENTION_GLOW};border-radius:8px;padding:12px 16px;"
        f"font-size:14px;line-height:1.5;color:{palette.FG};'>{html.escape(text)}</div>"
    )


def _band_count_html(text: str) -> str:
    return f"<span style='font-size:12px;color:{palette.FG_SUBTLE};font-weight:500;'>{html.escape(text)}</span>"


def _dot_html(kind: str) -> str:
    color = palette.ERR if kind == "err" else palette.WARN
    return f"<div style='width:6px;height:6px;border-radius:50%;background:{color};margin-left:8px;'></div>"


def _name_with_chip_html(name: str, marketplace: str) -> str:
    return (
        f"<div style='display:flex;align-items:center;gap:8px;min-width:0;'>"
        f"<span title='{html.escape(name, quote=True)}' style='font-size:14px;font-weight:600;"
        f"color:{palette.FG};{_SINGLE_LINE}'>{html.escape(name)}</span>"
        f"{palette.marketplace_chip_html(html.escape((marketplace or '').strip()))}</div>"
    )


def _one_line_html(text: str) -> str:
    """A wrapping cell stretches its row and breaks the grid; the full text lives in the tooltip."""
    return (
        f"<span title='{html.escape(text, quote=True)}' style='display:block;font-size:12.5px;"
        f"color:{palette.FG_MUTED};{_SINGLE_LINE}'>{html.escape(text)}</span>"
    )


def _two_line_html(title: str, subline: str) -> str:
    return (
        f"<div style='display:flex;flex-direction:column;min-width:0;'>"
        f"<span title='{html.escape(title, quote=True)}' style='font-size:13.5px;color:{palette.FG};"
        f"{_SINGLE_LINE}'>{html.escape(title)}</span>"
        f"<span title='{html.escape(subline, quote=True)}' style='font-size:12px;color:{palette.FG_SUBTLE};"
        f"{_SINGLE_LINE}'>{html.escape(subline)}</span></div>"
    )


def _cell_html(text: str, color: str = palette.FG_MUTED, align: str = "left") -> str:
    return (
        f"<div style='font-size:13px;color:{color};text-align:{align};white-space:nowrap;"
        f"font-variant-numeric:tabular-nums;'>{html.escape(text)}</div>"
    )


def _label_or(key: str, fallback: str) -> str:
    """The catalog text for `key`, or `fallback` for a value the catalog does not know yet."""
    text = i18n.t(key)
    return fallback if text == key else text


def _timestamp_or_none(raw) -> datetime | None:
    try:
        return parse_timestamp(raw)
    except (TypeError, ValueError):
        return None


def _date_or_none(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10]) if raw else None
    except ValueError:
        return None

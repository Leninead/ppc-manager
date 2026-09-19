"""Reusable picker of Search Term data: synced Amazon Ads profiles, or a manually uploaded report.

Every widget and session key starts with f"{key_prefix}_src_", so several modules can mount it side by side.
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from core.amazon_ads.raw_reports import REPORT_REQUESTS_TABLE
from core.date_labels import (  # noqa: F401 — el picker los re-exporta para sus consumidores
    data_of_day_phrase,
    date_range_label,
    day_phrase,
    short_date,
)
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, ReportReadError
from core.amazon_ads.sync_planner import BACKFILL_DAYS, PROFILE_NEEDS_REAUTH, profile_timezone
from core.integrations.store import StoreError, _Rest, _rest_credentials
from core.integrations.sync_jobs import SyncJob, SyncJobStore, parse_date, sanitize_error
from core.search_term.file import (
    FORMAT_CONSOLE_2026,
    FORMAT_CONSOLE_LEGACY,
    FileAccount,
    SearchTermFile,
    SearchTermFileError,
    read_search_term_file,
)
from core.search_term.frame import SearchTermSource
from core.ui import palette

log = logging.getLogger(__name__)

KEY_NAMES = (
    "card", "actions",
    "account", "profile", "profile_last", "period", "custom_range", "custom_range_last", "pinned", "loaded",
    "last_source", "manual", "refresh", "refresh_retrying", "refresh_busy", "refresh_feedback", "load_newer",
    "newer_box", "go_accounts", "upload_manual", "upload_meanwhile", "upload_failed", "back_to_api", "file",
    "file_account", "file_account_last",
)
# Choices re-stored every run: a run that does not draw them (a failed accounts read, manual mode) keeps them.
_KEPT_CHOICES = ("account", "profile", "period", "file_account")
LOADED_SOURCES_PER_PICKER = 4

PERIOD_PRESET_DAYS = (7, 14, 30, 60)
DEFAULT_PERIOD_DAYS = 7
MAX_PERIOD_DAYS = 60
CUSTOM_PERIOD_KEY = "custom"

STATE_READY = "ready"
STATE_UPDATING = "updating"
STATE_RETRYING = "retrying"
STATE_FAILED = "failed"
STATE_NEEDS_REAUTH = "needs_reauth"
STATE_FIRST_LOAD = "first_load"
STATE_FIRST_LOAD_FAILED = "first_load_failed"
_POLLING_STATES = (STATE_UPDATING, STATE_RETRYING, STATE_FIRST_LOAD)
_CLOSED_WITHOUT_DATA = ("failed", "cancelled")

FEEDBACK_TOAST = "toast"
FEEDBACK_WARNING = "warning"
FEEDBACK_ERROR = "error"

PROGRESS_DONE = "done"
PROGRESS_WORKING = "working"
PROGRESS_QUEUED = "queued"
PROGRESS_FAILED = "failed"

# The team works from Buenos Aires; profile-local days only matter for "data through".
DISPLAY_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
PROFILES_TTL_SECONDS = 60
STATUS_TTL_SECONDS = 30
SEARCH_TERMS_TTL_SECONDS = 6 * 3600
STATUS_POLL_INTERVAL = "30s"
_CONNECTED_ACCOUNTS_PAGE = "🔑 Cuentas conectadas"

# Alto del selectbox de BaseWeb: la fila de Cuenta / País / Período se mide contra él.
CONTROL_HEIGHT_PX = 40

BLOCK_TITLE = "Datos de Amazon Ads"
BLOCK_TAG = "Se actualiza solo · todos los días"
UPLOAD_LABEL = "Sube tu STR (.xlsx o .csv)"
NO_CONNECTION_HINT = (
    "Si conectás la cuenta en Sistema → Cuentas conectadas, este reporte se actualiza solo todos los días "
    "y no hace falta subir archivos."
)
NO_ACCOUNTS_MESSAGE = (
    "{module} necesita una cuenta de Amazon Ads conectada con datos. Conectala en Sistema → Cuentas conectadas."
)
MANUAL_MODE_NOTE = "Estás analizando un archivo subido a mano. No se guarda ni se mezcla con los datos de Amazon Ads."
FIRST_LOAD_MESSAGE = (
    f"Estamos trayendo el historial de esta cuenta ({BACKFILL_DAYS} días, lo máximo que guarda Amazon). "
    "Cuando termine se habilita el período y el resto del módulo."
)
ASK_AN_ADMIN = "Si sigue fallando, avisale a un admin."
FIRST_LOAD_FAILED_MESSAGE = (
    "La primera carga de esta cuenta no se pudo completar, así que todavía no hay datos para analizar."
)
FIRST_LOAD_FAILED_MANUAL_HINT = "Mientras tanto podés subir el archivo a mano."
KEPT_DATA_NOTE = "Seguís viendo los datos que ya estaban cargados."
ACCOUNTS_UNREADABLE_MESSAGE = (
    f"No aparece ninguna cuenta de Amazon Ads conectada; puede ser un corte momentáneo. {KEPT_DATA_NOTE} "
    f"{ASK_AN_ADMIN}"
)
NEWER_DATA_MESSAGE = "Hay datos más nuevos que los que estás viendo. Si los cargás, el análisis IA se vuelve a correr."
NEEDS_REAUTH_MESSAGE = (
    "Amazon rechazó la autorización de esta cuenta, así que no se puede actualizar. "
    "Hay que reautorizarla en Sistema → Cuentas conectadas."
)
PROFILE_UNAVAILABLE_MESSAGE = (
    "Esta cuenta no se puede actualizar ahora: revisá su estado en Sistema → Cuentas conectadas."
)
NO_DATABASE_MESSAGE = "No hay base de datos configurada, así que no se puede pedir la actualización."
REFRESH_FEEDBACK = {
    "created": (FEEDBACK_TOAST, "Actualización pedida"),
    "already_running": (FEEDBACK_TOAST, "Ya hay una actualización en curso"),
    "cooldown": (FEEDBACK_TOAST, "Se pidió hace menos de 30 minutos"),
}

_PHASE_LABELS = ("Pedido a Amazon", "Amazon generando el reporte", "Guardando los datos")
_PHASE_INDEX = {"requesting": 0, "waiting": 1, "saving": 2}
_CHUNK_PROGRESS = {
    "saved": (PROGRESS_DONE, "listo"),
    "requested": (PROGRESS_WORKING, "generando"),
    "saving": (PROGRESS_WORKING, "guardando"),
    "to_request": (PROGRESS_QUEUED, "en espera"),
    "failed": (PROGRESS_FAILED, "falló"),
}
_FILE_FORMAT_LABELS = {
    FORMAT_CONSOLE_2026: "formato nuevo de la consola",
    FORMAT_CONSOLE_LEGACY: "formato clásico de la consola",
}
_FILE_CURRENCY_COLUMNS = {FORMAT_CONSOLE_2026: "Budget currency", FORMAT_CONSOLE_LEGACY: "Currency"}


@dataclass(frozen=True)
class PeriodOption:
    key: str
    label: str
    days: int | None = None
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class ProgressStep:
    label: str
    state: str
    note: str = ""


def picker_key(key_prefix: str, name: str) -> str:
    if name not in KEY_NAMES:
        raise ValueError(f"unknown source picker key: {name!r}")
    return f"{key_prefix}_src_{name}"


def picker_keys(key_prefix: str) -> set[str]:
    return {picker_key(key_prefix, name) for name in KEY_NAMES}


def count_label(count: int) -> str:
    return f"{count:,}".replace(",", ".")


def profile_today(option: ProfileOption, now: datetime) -> date:
    return now.astimezone(profile_timezone(option.timezone, "")).date()


def period_options(data_from: date | None, data_through: date) -> list[PeriodOption]:
    """Presets ending at the last synced day, clipped to the data kept; the first preset covering it all closes the list."""
    earliest = data_from or data_through - timedelta(days=MAX_PERIOD_DAYS - 1)
    available_days = (data_through - earliest).days + 1
    options = []
    for days in PERIOD_PRESET_DAYS:
        start = max(earliest, data_through - timedelta(days=days - 1))
        options.append(PeriodOption(key=str(days), label=f"Últimos {days} días", days=days, start=start,
                                    end=data_through))
        if days >= available_days:
            break
    options.append(PeriodOption(key=CUSTOM_PERIOD_KEY, label="Personalizado"))
    return options


def default_period_key(options: list[PeriodOption]) -> str:
    presets = [option.key for option in options if option.key != CUSTOM_PERIOD_KEY]
    return str(DEFAULT_PERIOD_DAYS) if str(DEFAULT_PERIOD_DAYS) in presets else presets[-1]


def clip_custom_range(first: date, last: date, data_from: date | None, data_through: date) -> tuple[date, date]:
    start, end = sorted((first, last))
    earliest = data_from or data_through - timedelta(days=MAX_PERIOD_DAYS - 1)
    end = min(max(end, earliest), data_through)
    start = min(max(start, earliest), end)
    return max(start, end - timedelta(days=MAX_PERIOD_DAYS - 1)), end


def empty_period_message(period: PeriodOption, start: date, end: date, country_code: str) -> str:
    if period.days is not None and (end - start).days + 1 == period.days:
        when = f"en los últimos {period.days} días"
    else:
        when = f"entre el {short_date(start)} y el {short_date(end)}"
    where = f" en {country_code}" if country_code else ""
    return f"Esta cuenta no tuvo búsquedas con clicks {when}{where}. Probá con un período más largo u otro país."


def data_through_note(data_through: date, today: date) -> str:
    return f"Datos hasta {day_phrase(data_through, today)} (hora del perfil)"


def source_state(option: ProfileOption, latest_job: SyncJob | None, now: datetime) -> str:
    if option.status == PROFILE_NEEDS_REAUTH:
        return STATE_NEEDS_REAUTH
    if option.data_through is None:
        if latest_job is not None and latest_job.status in _CLOSED_WITHOUT_DATA:
            return STATE_FIRST_LOAD_FAILED
        return STATE_FIRST_LOAD
    if latest_job is None:
        return STATE_READY
    if latest_job.status in ("pending", "running"):
        return STATE_UPDATING
    # A later manual refresh failing does not make data refreshed today stale.
    is_fresh = option.refreshed_on is not None and option.refreshed_on >= profile_today(option, now)
    if latest_job.status == "retrying" and not is_fresh:
        return STATE_RETRYING
    if latest_job.status == "failed" and not is_fresh:
        return STATE_FAILED
    return STATE_READY


def freshness_pill(option: ProfileOption, latest_job: SyncJob | None, now: datetime) -> tuple[str, str]:
    """(status pill kind, label) for the block header."""
    state = source_state(option, latest_job, now)
    today = now.astimezone(DISPLAY_TIMEZONE).date()
    last_success = option.last_success_at.astimezone(DISPLAY_TIMEZONE) if option.last_success_at else None
    if state == STATE_FIRST_LOAD_FAILED:
        return "err", "La primera carga falló"
    if state in (STATE_NEEDS_REAUTH, STATE_FAILED):
        if last_success is None:
            return "err", "Sin actualizar"
        if last_success.date() == today:
            return "err", f"Sin actualizar desde hoy {last_success:%H:%M}"
        return "err", f"Sin actualizar desde {day_phrase(last_success.date(), today)}"
    if state == STATE_FIRST_LOAD:
        return "idle", "Primera carga en curso"
    if state == STATE_UPDATING:
        if latest_job.created_at is None:
            return "idle", "Actualizando"
        return "idle", f"Actualizando · pedido a las {latest_job.created_at.astimezone(DISPLAY_TIMEZONE):%H:%M}"
    if state == STATE_RETRYING:
        retry_at = latest_job.next_attempt_at.astimezone(DISPLAY_TIMEZONE) if latest_job.next_attempt_at else None
        retry = f"reintenta {retry_at:%H:%M}" if retry_at else "reintentando"
        if last_success is None:
            return "warn", retry.capitalize()
        return "warn", f"Datos {data_of_day_phrase(last_success.date(), today)} · {retry}"
    if last_success is None:
        return "ok", f"Datos hasta {day_phrase(option.data_through, profile_today(option, now))}"
    if last_success.date() == today:
        return "ok", f"Al día · actualizado hoy {last_success:%H:%M}"
    return "ok", f"Actualizado {day_phrase(last_success.date(), today)} {last_success:%H:%M}"


def first_load_failure_detail(option: ProfileOption, latest_job: SyncJob | None) -> str:
    """The recorded cause of a failed first load, scrubbed again before it reaches every user's screen."""
    recorded = ""
    if latest_job is not None:
        recorded = latest_job.error_message or latest_job.error_class
    recorded = (recorded or option.last_error).strip()
    if not recorded:
        return ""
    return sanitize_error(RuntimeError(recorded))[1]


def refresh_feedback(reason: str) -> tuple[str, str]:
    return REFRESH_FEEDBACK.get(reason, (FEEDBACK_WARNING, PROFILE_UNAVAILABLE_MESSAGE))


def has_newer_data(pinned: ProfileOption, current: ProfileOption) -> bool:
    if current.last_success_at is None:
        return False
    return pinned.last_success_at is None or current.last_success_at > pinned.last_success_at


def should_repin(pinned: ProfileOption | None) -> bool:
    """Nothing was loaded yet, so there is nothing to protect from a silent swap."""
    return pinned is None or pinned.data_through is None


def phase_steps(job: SyncJob) -> list[ProgressStep]:
    reached = _PHASE_INDEX.get(job.phase, 0)
    return [
        ProgressStep(label=label, state=PROGRESS_DONE if index < reached
                     else PROGRESS_WORKING if index == reached else PROGRESS_QUEUED)
        for index, label in enumerate(_PHASE_LABELS)
    ]


def chunk_progress(request_rows: list[dict]) -> list[ProgressStep]:
    steps = []
    for row in sorted(request_rows, key=lambda request: str(request.get("window_start") or "")):
        start, end = parse_date(row.get("window_start")), parse_date(row.get("window_end"))
        if start is None or end is None:
            continue
        state, note = _CHUNK_PROGRESS.get(row.get("status") or "", (PROGRESS_QUEUED, "en espera"))
        steps.append(ProgressStep(label=date_range_label(start, end, with_year=False), state=state, note=note))
    return steps


def group_by_label(profiles: list[ProfileOption]) -> dict[str, list[ProfileOption]]:
    groups: dict[str, list[ProfileOption]] = {}
    for option in profiles:
        groups.setdefault(option.label, []).append(option)
    return groups


def country_labels(profiles: list[ProfileOption]) -> dict[str, str]:
    """profile_id → pill label; a country repeated within one account also names the account type."""
    repeated = Counter(option.country_code for option in profiles)
    labels = {}
    for option in profiles:
        country = option.country_code or "—"
        if repeated[option.country_code] > 1:
            country = f"{country} · {option.account_type or option.account_name or option.profile_id}"
        labels[option.profile_id] = country
    return labels


def default_file_account(accounts: tuple[FileAccount, ...], current_key: str | None) -> str:
    if current_key in {account.key for account in accounts}:
        return current_key
    return max(accounts, key=lambda account: account.row_count).key


def file_account_label(account: FileAccount) -> str:
    return f"{account.name} · {count_label(account.row_count)} filas"


def file_summary(search_term_file: SearchTermFile) -> str:
    rows = sum(account.row_count for account in search_term_file.accounts)
    return f"{count_label(rows)} filas · {_FILE_FORMAT_LABELS.get(search_term_file.format, 'formato no reconocido')}"


def file_currency_html(file_format: str, currency_code: str) -> str:
    column = _FILE_CURRENCY_COLUMNS.get(file_format)
    if not currency_code or not column:
        return _muted_line_html(["Moneda no informada en el archivo"])
    return _muted_line_html([
        "Montos en", palette.marketplace_chip_html(html.escape(currency_code)),
        f"según la columna «{html.escape(column)}» del archivo",
    ], separator=" ")


def render_source_picker(key_prefix: str = "str", *, allow_manual: bool = True,
                         module_label: str = "Search Term Report") -> SearchTermSource | None:
    """Mounts the data source block; returns the Search Term data to analyze, or None while there is none.

    The returned frame is the caller's own copy: mutating it never changes what the picker keeps.
    """
    _keep_choices(key_prefix)
    profiles = _available_profiles()
    manual_mode = allow_manual and bool(st.session_state.get(picker_key(key_prefix, "manual")))
    if not profiles:
        last_source = _last_source(key_prefix)
        if last_source is not None and not manual_mode:
            st.warning(ACCOUNTS_UNREADABLE_MESSAGE)
            return _with_own_frame(last_source)
        if not allow_manual:
            st.info(NO_ACCOUNTS_MESSAGE.format(module=module_label))
            return None
        return _render_file_input(key_prefix, hint=NO_CONNECTION_HINT)
    if manual_mode:
        return _render_manual_mode(key_prefix)
    return _render_amazon_ads(key_prefix, profiles, allow_manual=allow_manual)


def _render_manual_mode(key_prefix: str) -> SearchTermSource | None:
    with st.container(border=True):
        note_col, back_col = st.columns([4.2, 1.8], vertical_alignment="center")
        note_col.markdown(MANUAL_MODE_NOTE)
        back_col.button("Volver a datos de Amazon Ads", key=picker_key(key_prefix, "back_to_api"),
                        type="tertiary", icon=":material/arrow_back:",
                        on_click=_set_manual_mode, args=(key_prefix, False))
        return _render_file_input(key_prefix, hint="")


def _render_file_input(key_prefix: str, *, hint: str) -> SearchTermSource | None:
    uploaded = st.file_uploader(UPLOAD_LABEL, type=["xlsx", "csv"], key=picker_key(key_prefix, "file"))
    if hint:
        st.caption(hint)
    if uploaded is None:
        return None
    file_bytes = uploaded.getvalue()
    try:
        search_term_file = _read_uploaded_file(file_bytes, uploaded.name)
    except SearchTermFileError as exc:
        st.error(str(exc))
        return None

    st.caption(file_summary(search_term_file))
    account_key = _choose_file_account(key_prefix, search_term_file)
    account = next(account for account in search_term_file.accounts if account.key == account_key)
    st.markdown(file_currency_html(search_term_file.format, account.currency_code), unsafe_allow_html=True)
    return search_term_file.source_for(account_key, file_name=uploaded.name,
                                       file_bytes_digest=hashlib.sha256(file_bytes).hexdigest())


def _choose_file_account(key_prefix: str, search_term_file: SearchTermFile) -> str:
    accounts = search_term_file.accounts
    if len(accounts) == 1:
        return accounts[0].key
    labels = {account.key: file_account_label(account) for account in accounts}
    chosen = _resolve_choice(key_prefix, "file_account", list(labels),
                             fallback=default_file_account(
                                 accounts, st.session_state.get(picker_key(key_prefix, "file_account_last"))))
    st.segmented_control("Cuenta del archivo", options=list(labels), format_func=labels.get,
                         key=picker_key(key_prefix, "file_account"))
    st.session_state[picker_key(key_prefix, "file_account_last")] = chosen
    return chosen


def _card_css(card_key: str) -> str:
    """El segmented control de País nace 8px más bajo que los dos selectbox de su fila."""
    return (f"<style>.st-key-{card_key} [data-testid='stButtonGroup'] button"
            f"{{height:{CONTROL_HEIGHT_PX}px;}}</style>")


def _actions_css(actions_key: str) -> str:
    """Las dos acciones, en fila y pegadas al borde derecho, cada una del ancho de su texto.

    Streamlit apila los botones de un contenedor y sólo sabe estirarlos a todo el ancho: en un
    panel angosto eso les parte la etiqueta en varias líneas y quedan de distinto alto.
    """
    # La clase st-key- la lleva el propio stVerticalBlock, no un contenedor padre.
    return (f"<style>.st-key-{actions_key}"
            f"{{flex-direction:row;justify-content:flex-end;align-items:center;gap:8px;}}"
            f".st-key-{actions_key} [data-testid='stElementContainer']{{width:auto;}}"
            f".st-key-{actions_key} button{{white-space:nowrap;}}</style>")


def _render_amazon_ads(key_prefix: str, profiles: list[ProfileOption], *,
                       allow_manual: bool) -> SearchTermSource | None:
    now = datetime.now(timezone.utc)
    groups = group_by_label(profiles)
    last_profile_id = st.session_state.get(picker_key(key_prefix, "profile_last"))
    last_label = next((option.label for option in profiles if option.profile_id == last_profile_id), None)
    account_label = _resolve_choice(key_prefix, "account", list(groups), fallback=last_label)
    account_profiles = groups[account_label]
    countries = country_labels(account_profiles)
    profile_id = _resolve_choice(key_prefix, "profile", list(countries), fallback=last_profile_id)
    current = next(option for option in account_profiles if option.profile_id == profile_id)
    pinned = _pinned_option(key_prefix, current)
    state = source_state(current, _latest_job(profile_id), now)

    card_key = picker_key(key_prefix, "card")
    st.markdown(_card_css(card_key), unsafe_allow_html=True)
    with st.container(border=True, key=card_key):
        # A fragment polls only the status block, never the analysis below it.
        status_block = st.fragment(run_every=STATUS_POLL_INTERVAL if state in _POLLING_STATES else None)(_render_status)
        status_block(key_prefix, profile_id, allow_manual)

        account_col, country_col, period_col = st.columns([2.2, 1.3, 1.6])
        account_col.selectbox("Cuenta", list(groups), key=picker_key(key_prefix, "account"))
        country_col.segmented_control("País", options=list(countries), format_func=countries.get,
                                      key=picker_key(key_prefix, "profile"))
        st.session_state[picker_key(key_prefix, "profile_last")] = profile_id
        if pinned.data_through is None:
            return None

        with period_col:
            period, start, end = _render_period(key_prefix, pinned)
        # The table keeps only the newest rows, so a range not in memory can only be read at the latest sync.
        if has_newer_data(pinned, current) and not _is_loaded(key_prefix, pinned, start, end):
            _pin(key_prefix, current)
            st.rerun()
        try:
            source = _pinned_search_terms(key_prefix, pinned, start, end)
        except ReportReadError as exc:
            last_source = _last_source(key_prefix, profile_id=profile_id)
            if last_source is None:
                st.error(str(exc))
                return None
            st.error(f"{exc} {KEPT_DATA_NOTE}")
            return _with_own_frame(last_source)

        _render_info_row(key_prefix, source, pinned, start, end, state=state, allow_manual=allow_manual, now=now)
        if source.frame.empty:
            st.info(empty_period_message(period, start, end, pinned.country_code))
            return None
    st.session_state[picker_key(key_prefix, "last_source")] = source
    return _with_own_frame(source)


def _render_status(key_prefix: str, profile_id: str, allow_manual: bool) -> None:
    _show_refresh_feedback(key_prefix)
    current = next((option for option in _available_profiles() if option.profile_id == profile_id), None)
    if current is None:
        return
    now = datetime.now(timezone.utc)
    latest_job = _latest_job(profile_id)
    pinned = st.session_state.get(picker_key(key_prefix, "pinned"), {}).get(profile_id, current)
    kind, label = freshness_pill(current, latest_job, now)
    st.markdown(palette.band_header_html(title=BLOCK_TITLE, tag=BLOCK_TAG,
                                         right=palette.status_pill_html(kind, html.escape(label))),
                unsafe_allow_html=True)
    if pinned.data_through is None and current.data_through is not None:
        st.rerun()

    state = source_state(current, latest_job, now)
    if state == STATE_FIRST_LOAD:
        _render_first_load(key_prefix, latest_job, allow_manual)
    elif state == STATE_FIRST_LOAD_FAILED:
        _render_first_load_failed(key_prefix, current, latest_job, allow_manual)
    elif state == STATE_UPDATING:
        _render_updating(key_prefix, latest_job, pinned, now)
    elif state == STATE_RETRYING:
        _render_retrying(key_prefix, current, now)
    elif state == STATE_NEEDS_REAUTH:
        _render_needs_reauth(key_prefix)
    elif state == STATE_FAILED:
        st.markdown(f"La última actualización no se pudo completar. Lo que ves son los datos "
                    f"{_loaded_data_phrase(current, now)}. {ASK_AN_ADMIN}")
    if has_newer_data(pinned, current):
        _render_newer_data(key_prefix, current)


def _render_first_load(key_prefix: str, latest_job: SyncJob | None, allow_manual: bool) -> None:
    st.markdown(FIRST_LOAD_MESSAGE)
    steps = chunk_progress(_report_requests(latest_job.id)) if latest_job is not None else []
    if steps:
        st.markdown(_progress_html(steps, done_color=palette.OK), unsafe_allow_html=True)
    if not allow_manual:
        return
    _, button_col = st.columns([3.6, 2.4])
    if button_col.button("Mientras tanto, subir archivo manualmente", key=picker_key(key_prefix, "upload_meanwhile"),
                         type="tertiary", icon=":material/upload:"):
        _set_manual_mode(key_prefix, True)
        st.rerun()


def _render_first_load_failed(key_prefix: str, current: ProfileOption, latest_job: SyncJob | None,
                              allow_manual: bool) -> None:
    text_col, button_col = st.columns([4.4, 1.6], vertical_alignment="center")
    sentences = [FIRST_LOAD_FAILED_MESSAGE, FIRST_LOAD_FAILED_MANUAL_HINT if allow_manual else "", ASK_AN_ADMIN]
    text_col.markdown(" ".join(sentence for sentence in sentences if sentence))
    detail = first_load_failure_detail(current, latest_job)
    if detail:
        text_col.markdown(_muted_line_html([html.escape(f"Motivo: {detail}")]), unsafe_allow_html=True)
    if allow_manual and button_col.button("Subir archivo manualmente", key=picker_key(key_prefix, "upload_failed"),
                                          type="tertiary", icon=":material/upload:"):
        _set_manual_mode(key_prefix, True)
        st.rerun()


def _render_updating(key_prefix: str, latest_job: SyncJob, pinned: ProfileOption, now: datetime) -> None:
    text_col, button_col = st.columns([4.4, 1.6], vertical_alignment="center")
    text_col.markdown("Amazon está armando el reporte. Puede tardar de minutos a algunas horas; mientras tanto "
                      f"seguís trabajando con los datos {_loaded_data_phrase(pinned, now)}.")
    button_col.button("Actualizando…", key=picker_key(key_prefix, "refresh_busy"), disabled=True,
                      icon=":material/hourglass_top:")
    st.markdown(_progress_html(phase_steps(latest_job), done_color=palette.ACCENT), unsafe_allow_html=True)


def _render_retrying(key_prefix: str, current: ProfileOption, now: datetime) -> None:
    text_col, button_col = st.columns([4.4, 1.6], vertical_alignment="center")
    text_col.markdown("La actualización de hoy no terminó y el sistema la vuelve a intentar sola hasta la noche. "
                      f"Lo que ves son los datos {_loaded_data_phrase(current, now)}. {ASK_AN_ADMIN}")
    button_col.button("Actualizar ahora", key=picker_key(key_prefix, "refresh_retrying"), icon=":material/refresh:",
                      on_click=_request_refresh, args=(key_prefix, current.profile_id))


def _render_needs_reauth(key_prefix: str) -> None:
    text_col, button_col = st.columns([4.4, 1.6], vertical_alignment="center")
    text_col.markdown(NEEDS_REAUTH_MESSAGE)
    if button_col.button("Ir a Cuentas conectadas", key=picker_key(key_prefix, "go_accounts"), type="tertiary",
                         icon=":material/key:"):
        st.session_state["selected_page"] = _CONNECTED_ACCOUNTS_PAGE
        st.rerun()


def _render_newer_data(key_prefix: str, current: ProfileOption) -> None:
    box_key = picker_key(key_prefix, "newer_box")
    st.markdown(f"<style>.st-key-{box_key}{{background:{palette.ROW_HOVER};border-radius:8px;"
                f"padding:12px 16px;}}</style>", unsafe_allow_html=True)
    with st.container(key=box_key):
        text_col, button_col = st.columns([4.4, 1.6], vertical_alignment="center")
        text_col.markdown(NEWER_DATA_MESSAGE)
        if button_col.button("Cargar datos nuevos", key=picker_key(key_prefix, "load_newer"), type="primary"):
            _pin(key_prefix, current)
            _forget_loaded(key_prefix, current.profile_id)
            st.rerun()


def _render_period(key_prefix: str, pinned: ProfileOption) -> tuple[PeriodOption, date, date]:
    options = {option.key: option for option in period_options(pinned.data_from, pinned.data_through)}
    period_key = _resolve_choice(key_prefix, "period", list(options),
                                 fallback=default_period_key(list(options.values())))
    st.selectbox("Período", list(options), format_func=lambda key: options[key].label,
                 key=picker_key(key_prefix, "period"))
    period = options[period_key]
    if period.key != CUSTOM_PERIOD_KEY:
        return period, period.start, period.end

    earliest = pinned.data_from or pinned.data_through - timedelta(days=MAX_PERIOD_DAYS - 1)
    # The last picked range is the widget default, so a run without the date input never falls back to 30 days.
    last_range = st.session_state.get(picker_key(key_prefix, "custom_range_last"))
    if last_range:
        default_range = clip_custom_range(*last_range, pinned.data_from, pinned.data_through)
    else:
        default_range = (max(earliest, pinned.data_through - timedelta(days=DEFAULT_PERIOD_DAYS - 1)),
                         pinned.data_through)
    picked = st.date_input("Rango", value=default_range, min_value=earliest,
                           max_value=pinned.data_through, format="DD/MM/YYYY",
                           key=picker_key(key_prefix, "custom_range"))
    dates = tuple(picked) if isinstance(picked, (tuple, list)) else (picked,)
    if len(dates) < 2:
        st.caption("Elegí también la fecha de fin.")
        dates = (dates[0], dates[0]) if dates else default_range
    else:
        st.session_state[picker_key(key_prefix, "custom_range_last")] = (dates[0], dates[1])
    start, end = clip_custom_range(dates[0], dates[1], pinned.data_from, pinned.data_through)
    if (end - start) < (max(dates) - min(dates)):
        st.caption(f"Máximo {MAX_PERIOD_DAYS} días: se usa del {short_date(start)} al {short_date(end)}.")
    return period, start, end


def _render_info_row(key_prefix: str, source: SearchTermSource, pinned: ProfileOption, start: date, end: date, *,
                     state: str, allow_manual: bool, now: datetime) -> None:
    # La columna de acciones entra dos botones sin que el más largo envuelva a dos líneas.
    info_col, actions_col = st.columns([4.2, 3.8], vertical_alignment="center")
    info_col.markdown(_muted_line_html([
        html.escape(date_range_label(start, end)),
        palette.marketplace_chip_html(html.escape(source.currency_code)),
        f"{count_label(len(source.frame))} términos",
        html.escape(data_through_note(pinned.data_through, profile_today(pinned, now))),
    ]), unsafe_allow_html=True)

    # Las dos acciones van juntas contra el borde derecho y con el mismo peso visual: son
    # alternativas entre sí, y una en tertiary se leía como enlace al lado de la otra.
    actions = []
    if allow_manual:
        actions.append(dict(label="Subir archivo manualmente", key=picker_key(key_prefix, "upload_manual"),
                            icon=":material/upload:", on_click=_set_manual_mode, args=(key_prefix, True)))
    if state in (STATE_READY, STATE_FAILED):
        actions.append(dict(label="Actualizar ahora", key=picker_key(key_prefix, "refresh"),
                            icon=":material/refresh:", on_click=_request_refresh,
                            args=(key_prefix, pinned.profile_id)))
    if not actions:
        return
    actions_key = picker_key(key_prefix, "actions")
    st.markdown(_actions_css(actions_key), unsafe_allow_html=True)
    with actions_col, st.container(key=actions_key):
        for action in actions:
            st.button(action["label"], key=action["key"], type="secondary", icon=action["icon"],
                      on_click=action["on_click"], args=action["args"])


def _resolve_choice(key_prefix: str, name: str, options: list[str], *, fallback: str | None) -> str:
    """The widget's value, written before it renders even when unchanged.

    A select widget whose option list changed comes back as a new widget; without the write it would show
    (and on the next rerun return) its first option instead of the choice.
    """
    key = picker_key(key_prefix, name)
    value = st.session_state.get(key)
    resolved = value if value in options else (fallback if fallback in options else options[0])
    st.session_state[key] = resolved
    return resolved


def _keep_choices(key_prefix: str) -> None:
    for name in _KEPT_CHOICES:
        key = picker_key(key_prefix, name)
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def _pinned_search_terms(key_prefix: str, pinned: ProfileOption, start: date, end: date) -> SearchTermSource:
    """The rows first read for this pin and range; a rerun never re-reads days the worker rewrote since."""
    loaded = st.session_state.setdefault(picker_key(key_prefix, "loaded"), {})
    load_key = _load_key(pinned, start, end)
    source = loaded.pop(load_key, None)
    if source is None:
        source = _load_search_terms(pinned, start, end)
    loaded[load_key] = source
    while len(loaded) > LOADED_SOURCES_PER_PICKER:
        loaded.pop(next(iter(loaded)))
    return source


def _load_key(pinned: ProfileOption, start: date, end: date) -> tuple:
    return pinned.profile_id, start, end, pinned.last_success_at


def _is_loaded(key_prefix: str, pinned: ProfileOption, start: date, end: date) -> bool:
    return _load_key(pinned, start, end) in st.session_state.get(picker_key(key_prefix, "loaded"), {})


def _pin(key_prefix: str, option: ProfileOption) -> None:
    st.session_state.setdefault(picker_key(key_prefix, "pinned"), {})[option.profile_id] = option


def _forget_loaded(key_prefix: str, profile_id: str) -> None:
    loaded = st.session_state.get(picker_key(key_prefix, "loaded"), {})
    for load_key in [load_key for load_key in loaded if load_key[0] == profile_id]:
        del loaded[load_key]


def _last_source(key_prefix: str, *, profile_id: str | None = None) -> SearchTermSource | None:
    last_source = st.session_state.get(picker_key(key_prefix, "last_source"))
    if last_source is None or (profile_id is not None and last_source.profile_id != profile_id):
        return None
    return last_source


def _with_own_frame(source: SearchTermSource) -> SearchTermSource:
    return dataclasses.replace(source, frame=source.frame.copy())


def _pinned_option(key_prefix: str, current: ProfileOption) -> ProfileOption:
    pinned = st.session_state.setdefault(picker_key(key_prefix, "pinned"), {}).get(current.profile_id)
    if should_repin(pinned):
        _pin(key_prefix, current)
        return current
    return pinned


def _set_manual_mode(key_prefix: str, enabled: bool) -> None:
    st.session_state[picker_key(key_prefix, "manual")] = enabled


def _request_refresh(key_prefix: str, profile_id: str) -> None:
    rest = _open_rest()
    if rest is None:
        feedback = (FEEDBACK_WARNING, NO_DATABASE_MESSAGE)
    else:
        try:
            outcome = SyncJobStore(rest).request_manual_refresh(profile_id, _current_username())
            feedback = refresh_feedback(outcome.reason)
        except StoreError as exc:
            feedback = (FEEDBACK_ERROR, str(exc))
    _load_latest_job.clear()
    st.session_state[picker_key(key_prefix, "refresh_feedback")] = feedback


def _show_refresh_feedback(key_prefix: str) -> None:
    feedback = st.session_state.pop(picker_key(key_prefix, "refresh_feedback"), None)
    if feedback is None:
        return
    kind, message = feedback
    if kind == FEEDBACK_TOAST:
        st.toast(message)
    elif kind == FEEDBACK_WARNING:
        st.warning(message)
    else:
        st.error(message)


def _loaded_data_phrase(option: ProfileOption, now: datetime) -> str:
    if option.last_success_at is None:
        return "que ya estaban cargados"
    loaded_at = option.last_success_at.astimezone(DISPLAY_TIMEZONE)
    return f"{data_of_day_phrase(loaded_at.date(), now.astimezone(DISPLAY_TIMEZONE).date())} {loaded_at:%H:%M}"


def _current_username() -> str:
    return str(st.session_state.get("username") or st.session_state.get("name") or "app")


def _muted_line_html(parts: list[str], separator: str = f" <span style='color:{palette.LINE}'>·</span> ") -> str:
    return (f"<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;"
            f"color:{palette.FG_MUTED};'>{separator.join(part for part in parts if part)}</div>")


def _progress_html(steps: list[ProgressStep], *, done_color: str) -> str:
    bars = {
        PROGRESS_DONE: done_color,
        PROGRESS_WORKING: f"linear-gradient(90deg,{palette.ACCENT} 50%,{palette.LINE_SOFT} 50%)",
        PROGRESS_QUEUED: palette.LINE_SOFT,
        PROGRESS_FAILED: palette.ERR,
    }
    note_colors = {PROGRESS_DONE: palette.OK_INK, PROGRESS_WORKING: palette.FG_MUTED,
                   PROGRESS_QUEUED: palette.FG_SUBTLE, PROGRESS_FAILED: palette.ERR_INK}
    cells = []
    for step in steps:
        label_color = palette.FG_SUBTLE if step.state == PROGRESS_QUEUED else palette.FG
        note = (f" <span style='color:{note_colors[step.state]};'>· {html.escape(step.note)}</span>"
                if step.note else "")
        cells.append(
            f"<div style='display:flex;flex-direction:column;gap:6px;'>"
            f"<div style='height:4px;border-radius:2px;background:{bars[step.state]};'></div>"
            f"<span style='font-size:12.5px;color:{label_color};'>{html.escape(step.label)}{note}</span></div>"
        )
    return (f"<div style='display:grid;grid-template-columns:repeat({len(steps)},minmax(0,1fr));gap:8px;"
            f"margin:4px 0 8px 0;'>{''.join(cells)}</div>")


def _open_rest() -> _Rest | None:
    credentials = _rest_credentials()
    return _Rest(*credentials) if credentials else None


def _available_profiles() -> list[ProfileOption]:
    try:
        return _load_profiles()
    except ReportReadError as exc:
        log.warning("Amazon Ads profiles could not be read, the picker falls back to manual upload: %s", exc)
        return []


def _latest_job(profile_id: str) -> SyncJob | None:
    try:
        return _load_latest_job(profile_id)
    except (requests.RequestException, ValueError) as exc:
        log.warning("Amazon Ads sync status unavailable for profile %s: %s", profile_id, exc)
        return None


def _report_requests(job_id: int) -> list[dict]:
    try:
        return _load_report_requests(job_id)
    except (requests.RequestException, ValueError) as exc:
        log.warning("Amazon Ads report progress unavailable for job %s: %s", job_id, exc)
        return []


@st.cache_data(ttl=PROFILES_TTL_SECONDS, show_spinner=False)
def _load_profiles() -> list[ProfileOption]:
    rest = _open_rest()
    return ReportProvider(rest).profiles() if rest is not None else []


@st.cache_data(ttl=STATUS_TTL_SECONDS, show_spinner=False)
def _load_latest_job(profile_id: str) -> SyncJob | None:
    rest = _open_rest()
    return SyncJobStore(rest).latest_for_profile(profile_id) if rest is not None else None


@st.cache_data(ttl=STATUS_TTL_SECONDS, show_spinner=False)
def _load_report_requests(job_id: int) -> list[dict]:
    rest = _open_rest()
    if rest is None:
        return []
    return rest.select(REPORT_REQUESTS_TABLE, {"select": "window_start,window_end,status", "job_id": f"eq.{job_id}",
                                               "order": "window_start.asc"})


@st.cache_data(ttl=SEARCH_TERMS_TTL_SECONDS, max_entries=16, show_spinner="Cargando datos de Amazon Ads…")
def _load_search_terms(option: ProfileOption, start: date, end: date) -> SearchTermSource:
    # The option carries last_success_at, so a newer sync is a new cache entry, never a silent swap.
    rest = _open_rest()
    if rest is None:
        raise ReportReadError("No hay base de datos configurada para leer los datos de Amazon Ads.")
    return ReportProvider(rest).search_terms(option, start, end)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _read_uploaded_file(file_bytes: bytes, file_name: str) -> SearchTermFile:
    return read_search_term_file(file_bytes, file_name)

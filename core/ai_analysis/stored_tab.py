"""La pestaña de un análisis guardado: buscarlo por huella y mostrar el estado que corresponda.

Los cuatro estados son los mismos para cualquier módulo — está guardado, se está generando, falló,
o no existe y hay que pedirlo — y el módulo sólo aporta cómo dibuja su resultado. M2 todavía tiene
su propia copia de esto con sus textos; migrarla es el paso siguiente, no parte de este cambio.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
import streamlit as st

from core.ai_analysis.store import TRIGGER_SCHEDULED, AiAnalysisStore
from core.date_labels import date_range_label
from core.integrations.store import StoreError
from core.integrations.sync_jobs import SyncJobStore

log = logging.getLogger(__name__)

STATUS_TTL_SECONDS = 15
GENERATING_POLL = "10s"
DISPLAY_TIMEZONE = None  # lo fija el llamador; sin zona se muestra la hora tal cual llega
REQUEST_FEEDBACK = {
    "created": "Análisis IA pedido: se genera en unos minutos.",
    "already_running": "Ya se está generando el análisis de estos datos.",
    "already_done": "Ya existe el análisis de estos datos.",
}
READ_FAILED = "No se pudo leer el análisis IA guardado. Probá de nuevo en unos segundos."
# Por qué la base rechazó el pedido. Un mensaje sin causa deja al AM sin nada que hacer y a quien
# mira el problema sin por dónde empezar.
REQUEST_REFUSED = {
    "invalid_request": ("La base no acepta pedidos de análisis para este módulo todavía: falta correr la "
                        "migración que lo habilita. Avisale a un admin."),
    "profile_unavailable": ("Esta cuenta no está activa o todavía no tiene datos sincronizados, así que no se "
                            "puede pedir el análisis."),
    "invalid_window": "El período elegido no entra en los datos sincronizados de esta cuenta.",
}
REQUEST_REFUSED_UNKNOWN = "No se pudo pedir el análisis para esta cuenta o este período ({reason})."
NO_DATABASE = "No hay base de datos configurada para pedir el análisis."
PENDING_TITLE = "Análisis IA pendiente"
PENDING_AUTO = ("Todavía no hay un análisis de estos datos. Se genera solo cuando llegan datos nuevos de Amazon "
                "Ads; si no querés esperar, pedilo ahora.")
PENDING_CUSTOM = ("No hay un análisis con estos parámetros o este período. Generalo para esta configuración: "
                  "los parámetros quedan guardados para la cuenta.")


@dataclass(frozen=True)
class StoredTabResult:
    analysis: object | None
    state: str


STATE_CURRENT = "current"
STATE_RUNNING = "running"
STATE_FAILED = "failed"
STATE_MISSING = "missing"


def _store(open_rest):
    rest = open_rest()
    return AiAnalysisStore(rest) if rest is not None else None


@st.cache_data(ttl=STATUS_TTL_SECONDS, show_spinner=False)
def _stored(module, profile_id, input_digest, _open_rest):
    store = _store(_open_rest)
    return store.done_for_input(module, profile_id, input_digest) if store is not None else None


@st.cache_data(ttl=STATUS_TTL_SECONDS, show_spinner=False)
def _job(module, profile_id, input_digest, _open_rest):
    store = _store(_open_rest)
    return store.latest_job_for_input(module, profile_id, input_digest) if store is not None else None


@st.cache_data(ttl=60, show_spinner=False)
def _settings(module, profile_id, _open_rest):
    store = _store(_open_rest)
    return store.settings(module, profile_id) if store is not None else None


def forget_reads() -> None:
    for loader in (_stored, _job, _settings):
        loader.clear()


def analysis_caption(stored, timezone=None) -> str:
    finished = stored.finished_at.astimezone(timezone) if (stored.finished_at and timezone) else stored.finished_at
    moment = finished.strftime("%d/%m %H:%M") if finished else "?"
    origin = ("generado automáticamente al llegar los datos" if stored.trigger == TRIGGER_SCHEDULED
              else f"pedido por {stored.requested_by}")
    return (f"Análisis del {date_range_label(stored.window_start, stored.window_end)} · {origin} · "
            f"listo el {moment}.")


def render_stored_analysis(*, module: str, key_prefix: str, source, input_digest: str, params, account_params,
                           open_rest, current_username, render_result, timezone=None) -> StoredTabResult:
    """Muestra el análisis guardado de exactamente estos datos y parámetros, nunca uno anterior."""
    feedback_key = f"{key_prefix}_ai_request_feedback"
    feedback = st.session_state.pop(feedback_key, None)
    if feedback:
        st.toast(feedback)
    try:
        stored = _stored(module, source.profile_id, input_digest, open_rest)
        job = None if stored is not None else _job(module, source.profile_id, input_digest, open_rest)
    except (requests.RequestException, StoreError) as exc:
        log.warning("stored analysis for %s could not be read: %s", source.profile_id, exc)
        st.error(READ_FAILED)
        return StoredTabResult(None, STATE_MISSING)

    if stored is not None:
        st.caption(analysis_caption(stored, timezone))
        render_result(stored)
        return StoredTabResult(stored, STATE_CURRENT)
    if job is not None and job.is_open:
        _render_generating(module, source.profile_id, input_digest, job, open_rest, timezone)
        return StoredTabResult(None, STATE_RUNNING)
    if job is not None and job.status == "failed":
        # Sin reintento, un análisis fallido deja la pantalla sin ninguna salida: ni se ve, ni se pide.
        st.error(f"El análisis IA de estos datos falló: {job.error_message or job.error_class}")
        if st.button("Reintentar", key=f"{key_prefix}_ai_retry_job"):
            _retry(job, open_rest, current_username)
        return StoredTabResult(None, STATE_FAILED)
    _render_request(module, key_prefix, source, input_digest, params, account_params, open_rest, current_username,
                    feedback_key)
    return StoredTabResult(None, STATE_MISSING)


def _retry(job, open_rest, current_username) -> None:
    rest = open_rest()
    if rest is None:
        st.error(NO_DATABASE)
        return
    try:
        SyncJobStore(rest).retry(job.id, current_username())
    except StoreError as exc:
        st.error(str(exc))
        return
    forget_reads()
    st.rerun()


def _render_generating(module, profile_id, input_digest, job, open_rest, timezone) -> None:
    @st.fragment(run_every=GENERATING_POLL)
    def _poll():
        _stored.clear()
        _job.clear()
        current = _job(module, profile_id, input_digest, open_rest) or job
        if _stored(module, profile_id, input_digest, open_rest) is not None or not current.is_open:
            st.rerun()
        created = current.created_at.astimezone(timezone) if (current.created_at and timezone) else current.created_at
        requested = created.strftime("%H:%M") if created else "?"
        st.status(f"Generando el análisis IA de estos datos · pedido a las {requested}. "
                  "Puede tardar unos minutos.", state="running")

    _poll()


def _render_request(module, key_prefix, source, input_digest, params, account_params, open_rest, current_username,
                    feedback_key) -> None:
    from core import ai_tab

    body = PENDING_AUTO if params == account_params else PENDING_CUSTOM
    st.markdown(ai_tab.ai_notice_html(PENDING_TITLE, body), unsafe_allow_html=True)
    if not st.button("Generar análisis IA", key=f"{key_prefix}_ai_request", type="primary"):
        return
    store = _store(open_rest)
    if store is None or source.window_start is None or source.window_end is None:
        st.error(NO_DATABASE)
        return
    username = current_username()
    try:
        if params != account_params:
            store.save_settings(module, source.profile_id, params.as_dict(), username)
        outcome = store.request_analysis(
            module, source.profile_id, window_start=source.window_start, window_end=source.window_end,
            lang="es", params=params.as_dict(), input_digest=input_digest, requested_by=username)
    except StoreError as exc:
        st.error(str(exc))
        return
    forget_reads()
    message = REQUEST_FEEDBACK.get(outcome.reason)
    if message is None:
        st.warning(REQUEST_REFUSED.get(outcome.reason,
                                       REQUEST_REFUSED_UNKNOWN.format(reason=outcome.reason)))
        return
    # A toast sent right before st.rerun() is dropped with the run; the next run shows it.
    st.session_state[feedback_key] = message
    st.rerun()

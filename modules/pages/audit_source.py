"""PPC Audit Pro's source block: the synced Amazon Ads data of one account and period, or a Bulk File by hand.

With connected accounts the Search Term picker chooses account, country and period, and the campaign structure of
that same account and window is read below it (core/ppc_audit/synced_reads.py): one choice, never two that disagree.
Without accounts, or when the AM asks, the Bulk File uploader of always.
"""
from __future__ import annotations

import hashlib
import html
import logging
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.date_labels import day_phrase, short_date
from core.ppc_audit.bulk_file import frames_from_bulk_file
from core.ppc_audit.frames import AuditFrames
from core.ppc_audit.synced_reads import SyncedAudit, read_synced_audit
from core.search_term.frame import SearchTermSource
from core.ui import palette
from modules.pages import search_term_source
from modules.pages.search_term_source import (
    ASK_AN_ADMIN,
    DISPLAY_TIMEZONE,
    NO_CONNECTION_HINT,
    count_label,
    picker_key,
    render_source_picker,
    shows_older_data,
)

log = logging.getLogger(__name__)

KEY_PREFIX = "audit"
STRUCTURE_PREFIX = "audit_structure"
MODULE_LABEL = "PPC Audit Pro"
BULK_UPLOADER_KEY = "audit_bulk"
BULK_UPLOAD_LABEL = "📦 Bulk File (.xlsx)"
STRUCTURE_TTL_SECONDS = 15 * 60
STRUCTURE_TITLE = "Estructura de las campañas"
STRUCTURE_TAG = "Misma cuenta y período"
BULK_MODE_NOTE = ("Estás auditando un Bulk File subido a mano. No se guarda ni se mezcla con los datos de "
                  "Amazon Ads.")
BULK_FALLBACK_HINT = "Mientras tanto podés subir el Bulk File a mano."
NO_DATABASE_MESSAGE = "No hay base de datos configurada para leer la estructura de las campañas."
UNREADABLE_FILE_MESSAGE = ("No se pudo leer el archivo. Subí el Bulk File (.xlsx) tal como lo exporta Campaign "
                           "Manager → Bulk Operations.")
ACCOUNT_NOT_LISTED_MESSAGE = "No se pudo leer la cuenta elegida en la lista de cuentas de Amazon Ads."


@dataclass(frozen=True, eq=False)
class AuditSource:
    frames: AuditFrames
    # "Cuenta · país" for Amazon Ads, the file name for a Bulk File.
    label: str
    # What changes when the data under the audit does, not when a value on screen does.
    signature: str
    profile_id: str = ""
    country_code: str = ""
    window_start: date | None = None
    window_end: date | None = None
    attribution_days: int | None = None
    # The picker keeps on screen data older than the account's latest sync.
    older_data: bool = False

    @property
    def from_amazon_ads(self) -> bool:
        return not self.frames.from_file


def render_audit_source() -> AuditSource | None:
    """Mounts the source block; returns what to audit, or None while there is nothing."""
    search_term_source._keep_choices(KEY_PREFIX)
    profiles = search_term_source._available_profiles()
    if not profiles:
        return _render_bulk_upload(hint=NO_CONNECTION_HINT)
    if st.session_state.get(picker_key(KEY_PREFIX, "manual")):
        return _render_bulk_mode()
    search_terms = render_source_picker(KEY_PREFIX, allow_manual=False, module_label=MODULE_LABEL)
    if search_terms is None:
        _render_bulk_action()
        return None
    option = next((profile for profile in profiles if profile.profile_id == search_terms.profile_id), None)
    if option is None:
        st.error(f"{ACCOUNT_NOT_LISTED_MESSAGE} {ASK_AN_ADMIN}")
        _render_bulk_action()
        return None
    return _render_structure(option, search_terms)


def listing_moment(listed_at: datetime, now: datetime) -> str:
    """"hoy 06:12", in the team's timezone."""
    local = listed_at.astimezone(DISPLAY_TIMEZONE)
    return f"{day_phrase(local.date(), now.astimezone(DISPLAY_TIMEZONE).date())} {local:%H:%M}"


def lag_notes(synced: SyncedAudit, window_end: date) -> list[str]:
    """What the metrics of the period lack: a report that stops before the period ends or never synced."""
    notes = []
    for what, through in (("campañas", synced.campaigns_through), ("keywords y targets", synced.targeting_through)):
        if through is None:
            notes.append(f"Las métricas de {what} de Sponsored Products todavía no se sincronizaron.")
        elif through < window_end:
            notes.append(f"Las métricas de {what} llegan hasta el {short_date(through)}: los días siguientes del "
                         "período no están en sus cifras.")
    return notes


def _render_structure(option: ProfileOption, search_terms: SearchTermSource) -> AuditSource | None:
    with st.container(border=True, key=picker_key(STRUCTURE_PREFIX, "card")):
        header = st.empty()
        try:
            synced = _load_synced_audit(option, search_terms.window_start, search_terms.window_end,
                                        search_terms.signature, search_terms.attribution_days,
                                        _search_terms=search_terms.frame)
        except ReportReadError as exc:
            log.warning("ppc audit: structure unreadable for profile %s: %s", option.profile_id, exc)
            header.markdown(_header_html("err", "No se pudo leer"), unsafe_allow_html=True)
            st.error(f"{exc} {ASK_AN_ADMIN}")
            _render_bulk_action()
            return None
        if synced.frames is None:
            header.markdown(_header_html("err" if synced.refused else "warn",
                                         "Sin permiso" if synced.refused else "Sin listar"), unsafe_allow_html=True)
            st.caption(f"{synced.missing_reason} {BULK_FALLBACK_HINT}")
            _render_bulk_action()
            return None

        now = datetime.now(timezone.utc)
        header.markdown(_header_html("ok", f"Listada {listing_moment(synced.listed_at, now)}"),
                        unsafe_allow_html=True)
        frames = synced.frames
        info_col, action_col = st.columns([4.2, 3.8], vertical_alignment="center")
        info_col.markdown(search_term_source._muted_line_html([html.escape(part) for part in _counts(frames)]),
                          unsafe_allow_html=True)
        with action_col:
            _render_bulk_action()
        for note in lag_notes(synced, search_terms.window_end):
            st.caption(note)
    return AuditSource(
        frames=frames, label=search_terms.label,
        signature="|".join(str(part) for part in (search_terms.signature, synced.listed_at, synced.campaigns_through,
                                                 synced.targeting_through, synced.sb_search_terms_through)),
        profile_id=option.profile_id, country_code=option.country_code,
        window_start=search_terms.window_start, window_end=search_terms.window_end,
        attribution_days=search_terms.attribution_days,
        older_data=shows_older_data(KEY_PREFIX, option.profile_id),
    )


def _counts(frames: AuditFrames) -> list[str]:
    parts = [f"{count_label(len(frames.sp_campaigns))} campañas SP",
             f"{count_label(len(frames.sp_keywords))} keywords",
             f"{count_label(len(frames.sp_product_targets))} product targets"]
    parts += [f"{product} {count_label(len(campaigns))}" for product, campaigns
              in (("SB", frames.sb_campaigns), ("SD", frames.sd_campaigns)) if len(campaigns)]
    return parts


def _header_html(kind: str, label: str) -> str:
    return palette.band_header_html(title=STRUCTURE_TITLE, tag=STRUCTURE_TAG,
                                    right=palette.status_pill_html(kind, html.escape(label)))


def _render_bulk_action() -> None:
    actions_key = picker_key(STRUCTURE_PREFIX, "actions")
    st.markdown(search_term_source._actions_css(actions_key), unsafe_allow_html=True)
    with st.container(key=actions_key):
        st.button("Subir Bulk File a mano", key=picker_key(STRUCTURE_PREFIX, "upload_manual"), type="secondary",
                  icon=":material/upload:", on_click=search_term_source._set_manual_mode, args=(KEY_PREFIX, True))


def _render_bulk_mode() -> AuditSource | None:
    with st.container(border=True):
        note_col, back_col = st.columns([4.2, 1.8], vertical_alignment="center")
        note_col.markdown(BULK_MODE_NOTE)
        back_col.button("Volver a datos de Amazon Ads", key=picker_key(KEY_PREFIX, "back_to_api"), type="tertiary",
                        icon=":material/arrow_back:", on_click=search_term_source._set_manual_mode,
                        args=(KEY_PREFIX, False))
        return _render_bulk_upload(hint="")


def _render_bulk_upload(*, hint: str) -> AuditSource | None:
    uploaded = st.file_uploader(BULK_UPLOAD_LABEL, type=["xlsx"], key=BULK_UPLOADER_KEY)
    if hint:
        st.caption(hint)
    if uploaded is None:
        _render_empty_state()
        return None
    file_bytes = uploaded.getvalue()
    try:
        frames = _read_bulk_file(file_bytes, uploaded.name)
    except (ValueError, zipfile.BadZipFile, OSError) as exc:
        log.warning("ppc audit: bulk file %s could not be read: %s", uploaded.name, exc)
        st.error(UNREADABLE_FILE_MESSAGE)
        return None
    return AuditSource(frames=frames, label=uploaded.name, signature=hashlib.sha256(file_bytes).hexdigest()[:16])


def _render_empty_state() -> None:
    st.markdown(
        "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
        "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
        "<div style='font-size:1.5rem;'>📦</div>"
        "<div style='font-weight:600;margin-top:0.5rem;'>Subí el Bulk File</div>"
        "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
        "Amazon Advertising → Campaign Manager → Bulk Operations "
        "→ Create spreadsheet for download</div>"
        "</div>",
        unsafe_allow_html=True,
    )


@st.cache_data(max_entries=3, ttl=3600, show_spinner="Leyendo el Bulk File…")
def _read_bulk_file(file_bytes: bytes, file_name: str) -> AuditFrames:
    return frames_from_bulk_file(file_bytes)


# The search terms are the picker's own rows: their signature, not the frame, keys the cache.
@st.cache_data(ttl=STRUCTURE_TTL_SECONDS, max_entries=8, show_spinner="Leyendo la estructura de las campañas…")
def _load_synced_audit(option: ProfileOption, start: date, end: date, search_terms_signature: str,
                       attribution_days: int, _search_terms: pd.DataFrame) -> SyncedAudit:
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    return read_synced_audit(rest, option, start, end, _search_terms, attribution_days=attribution_days)

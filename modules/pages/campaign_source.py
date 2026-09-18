"""Picker of campaign data: synced Amazon Ads campaigns, or a Campaign CSV uploaded by hand.

Looks like the Search Term picker and reuses its widgets and freshness rules under its own key prefix.
The freshness comes from the campaign sync jobs themselves: the search-term sync says nothing about them.
"""
from __future__ import annotations

import html
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd
import requests
import streamlit as st

from core.amazon_ads.campaign_provider import CampaignProvider, CampaignSource, campaign_sync_view
from core.amazon_ads.product_provider import IdleTargets, ProductCampaigns, ProductProvider
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.sync_planner import CAMPAIGNS_KIND, PRODUCT_CAMPAIGN_KINDS, PROFILE_NEEDS_REAUTH
from core.date_labels import date_range_label
from core.integrations.store import _error_message
from core.integrations.sync_jobs import SyncJob, SyncJobStore
from core.ui import palette
from modules.pages import search_term_source
from modules.pages.search_term_source import (
    ASK_AN_ADMIN,
    BLOCK_TAG,
    BLOCK_TITLE,
    FIRST_LOAD_FAILED_MANUAL_HINT,
    MANUAL_MODE_NOTE,
    NEEDS_REAUTH_MESSAGE,
    NO_CONNECTION_HINT,
    STATE_FIRST_LOAD_FAILED,
    STATUS_POLL_INTERVAL,
    STATUS_TTL_SECONDS,
    count_label,
    country_labels,
    data_through_note,
    freshness_pill,
    group_by_label,
    picker_key,
    profile_today,
    source_state,
)

log = logging.getLogger(__name__)

UPLOAD_LABEL = "Sube tu Bulk o Campaign CSV (.xlsx o .csv)"
CAMPAIGNS_TTL_SECONDS = 60 * 60
# SB, SD and targets sync on their own schedule; a short TTL picks up a finished sync without a key for each.
PRODUCTS_TTL_SECONDS = 15 * 60
PRODUCTS_UNREADABLE_NOTE = "No se pudieron leer las campañas SB y SD ni los targets; se muestra sólo Sponsored Products."
NO_CAMPAIGN_DATA_MESSAGE = (
    "Todavía no hay métricas de campañas de esta cuenta: se sincronizan una vez por día. "
    "Mientras tanto podés subir el Campaign CSV a mano."
)
FIRST_LOAD_MESSAGE = "Estamos trayendo las campañas de esta cuenta. Cuando termine se habilita el período."
FIRST_LOAD_FAILED_MESSAGE = (
    "La primera carga de campañas de esta cuenta no se pudo completar, así que todavía no hay datos para analizar."
)
NO_CAMPAIGNS_MESSAGE = "Esta cuenta no tiene campañas de Sponsored Products habilitadas ni pausadas."
NO_DATABASE_MESSAGE = "No hay base de datos configurada para leer las campañas de Amazon Ads."
UNREADABLE_FILE_MESSAGE = "No se pudo leer el archivo. Subí el Campaign CSV o el Bulk tal como los exporta Amazon."


@dataclass(frozen=True)
class CampaignInput:
    frame: pd.DataFrame
    # Empty for a file: its currency is not known, and the module keeps the dollar sign it always showed.
    currency_code: str
    # The synced read behind `frame` (account, window, signal inputs); None for a file uploaded by hand.
    source: CampaignSource | None = None
    # Sponsored Brands and Display campaigns, and the targets without impressions ("Target Graduation").
    # Apart from `frame`, which stays Sponsored Products: its signal inputs and sync are SP's own.
    products: ProductCampaigns | None = None
    idle_targets: IdleTargets | None = None


def render_campaign_source(key_prefix: str) -> CampaignInput | None:
    """Mounts the data source block; returns the campaigns to analyze, or None while there are none."""
    search_term_source._keep_choices(key_prefix)
    profiles = search_term_source._available_profiles()
    if not profiles:
        return _render_file_input(key_prefix, hint=NO_CONNECTION_HINT)
    if st.session_state.get(picker_key(key_prefix, "manual")):
        return _render_manual_mode(key_prefix)
    return _render_amazon_ads(key_prefix, profiles)


def campaign_pill(view: ProfileOption, latest_job: SyncJob | None, now: datetime) -> tuple[str, str]:
    """The STR picker's freshness pill, day and hour included, read from the campaign sync."""
    # Before the first campaign job exists there is no load in course to announce.
    if view.data_through is None and latest_job is None and view.status != PROFILE_NEEDS_REAUTH:
        return "idle", "Sin datos todavía"
    return freshness_pill(view, latest_job, now)


def campaign_count_label(sp_count: int, products: ProductCampaigns | None) -> str:
    """"264 campañas", or with SB / SD "264 campañas · SB 385 · SD 131"."""
    label = f"{count_label(sp_count)} campañas"
    if products is None or products.frame.empty:
        return label
    counts = products.frame["Type"].value_counts()
    parts = [f"{short} {count_label(int(counts[name]))}" for short, name in
             (("SB", "Sponsored Brands"), ("SD", "Sponsored Display")) if counts.get(name, 0)]
    return " · ".join([label, *parts])


def read_campaign_file(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    """The uploaded Bulk or Campaign CSV, read the way this module always read it."""
    buffer = io.BytesIO(file_bytes)
    return pd.read_excel(buffer) if file_name.endswith(".xlsx") else pd.read_csv(buffer)


def _render_amazon_ads(key_prefix: str, profiles: list[ProfileOption]) -> CampaignInput | None:
    groups = group_by_label(profiles)
    last_profile_id = st.session_state.get(picker_key(key_prefix, "profile_last"))
    last_label = next((option.label for option in profiles if option.profile_id == last_profile_id), None)
    account_label = search_term_source._resolve_choice(key_prefix, "account", list(groups), fallback=last_label)
    account_profiles = groups[account_label]
    countries = country_labels(account_profiles)
    profile_id = search_term_source._resolve_choice(key_prefix, "profile", list(countries),
                                                    fallback=last_profile_id)
    option = next(profile for profile in account_profiles if profile.profile_id == profile_id)
    now = datetime.now(timezone.utc)

    sync_error = None
    latest_job, completed = None, None
    try:
        latest_job, completed = _load_campaign_sync(profile_id)
    except ReportReadError as exc:
        sync_error = exc
    view = campaign_sync_view(option, completed)

    card_key = picker_key(key_prefix, "card")
    st.markdown(search_term_source._card_css(card_key), unsafe_allow_html=True)
    with st.container(border=True, key=card_key):
        polling = latest_job is not None and latest_job.is_open
        # A fragment polls only the header while a campaign job is open, never the analysis below it.
        st.fragment(run_every=STATUS_POLL_INTERVAL if polling else None)(_render_header)(
            option, sync_error is not None, polling)

        account_col, country_col, period_col = st.columns([2.2, 1.3, 1.6])
        account_col.selectbox("Cuenta", list(groups), key=picker_key(key_prefix, "account"))
        country_col.segmented_control("País", options=list(countries), format_func=countries.get,
                                      key=picker_key(key_prefix, "profile"))
        st.session_state[picker_key(key_prefix, "profile_last")] = profile_id

        if sync_error is not None:
            st.error(f"{sync_error} {ASK_AN_ADMIN}")
            _render_upload_action(key_prefix)
            return None
        if view.data_through is None:
            _render_without_data(view, latest_job, now)
            _render_upload_action(key_prefix)
            return None

        with period_col:
            _, start, end = search_term_source._render_period(key_prefix, view)
        try:
            source = _load_campaigns(option, start, end, view.last_success_at)
        except ReportReadError as exc:
            st.error(f"{exc} {ASK_AN_ADMIN}")
            _render_upload_action(key_prefix)
            return None

        products, idle_targets = _load_extras(profile_id, start, end)
        _render_info_row(key_prefix, source, view, now, products)
        if source.frame.empty and (products is None or products.frame.empty):
            st.info(NO_CAMPAIGNS_MESSAGE)
            return None
    return CampaignInput(frame=source.frame, currency_code=source.currency_code, source=source,
                         products=products, idle_targets=idle_targets)


def _load_extras(profile_id: str, start: date, end: date) -> tuple[ProductCampaigns | None, IdleTargets | None]:
    """SB / SD campaigns and idle targets; a failure here leaves the Sponsored Products page intact."""
    try:
        return _load_products(profile_id, start, end, _load_products_sync(profile_id))
    except ReportReadError as exc:
        log.warning("campaign extras unreadable for profile %s: %s", profile_id, exc)
        st.caption(PRODUCTS_UNREADABLE_NOTE)
        return None, None


def _render_header(option: ProfileOption, sync_unreadable: bool, polling: bool) -> None:
    kind, label = "err", "No se pudo leer"
    if not sync_unreadable:
        try:
            # Cached for a few seconds, so each poll re-reads the jobs without hammering the base.
            latest_job, completed = _load_campaign_sync(option.profile_id)
        except ReportReadError as exc:
            log.warning("campaign sync status unreadable for profile %s: %s", option.profile_id, exc)
        else:
            if polling and not (latest_job is not None and latest_job.is_open):
                # The polled job closed: the body below still shows what it said before, so redraw it all.
                st.rerun()
            kind, label = campaign_pill(campaign_sync_view(option, completed), latest_job, datetime.now(timezone.utc))
    st.markdown(palette.band_header_html(title=BLOCK_TITLE, tag=BLOCK_TAG,
                                         right=palette.status_pill_html(kind, html.escape(label))),
                unsafe_allow_html=True)
    if option.status == PROFILE_NEEDS_REAUTH:
        st.warning(NEEDS_REAUTH_MESSAGE)


def _render_without_data(view: ProfileOption, latest_job: SyncJob | None, now: datetime) -> None:
    if latest_job is None:
        st.info(NO_CAMPAIGN_DATA_MESSAGE)
    elif source_state(view, latest_job, now) == STATE_FIRST_LOAD_FAILED:
        st.error(f"{FIRST_LOAD_FAILED_MESSAGE} {FIRST_LOAD_FAILED_MANUAL_HINT}")
    else:
        st.info(FIRST_LOAD_MESSAGE)


def _render_info_row(key_prefix: str, source: CampaignSource, view: ProfileOption, now: datetime,
                     products: ProductCampaigns | None = None) -> None:
    info_col, action_col = st.columns([4.2, 3.8], vertical_alignment="center")
    info_col.markdown(search_term_source._muted_line_html([
        html.escape(date_range_label(source.window_start, source.window_end)),
        palette.marketplace_chip_html(html.escape(source.currency_code)),
        html.escape(campaign_count_label(len(source.frame), products)),
        html.escape(data_through_note(view.data_through, profile_today(view, now))),
    ]), unsafe_allow_html=True)
    with action_col:
        _render_upload_action(key_prefix)


def _render_upload_action(key_prefix: str) -> None:
    actions_key = picker_key(key_prefix, "actions")
    st.markdown(search_term_source._actions_css(actions_key), unsafe_allow_html=True)
    with st.container(key=actions_key):
        st.button("Subir archivo manualmente", key=picker_key(key_prefix, "upload_manual"), type="secondary",
                  icon=":material/upload:", on_click=search_term_source._set_manual_mode, args=(key_prefix, True))


def _render_manual_mode(key_prefix: str) -> CampaignInput | None:
    with st.container(border=True):
        note_col, back_col = st.columns([4.2, 1.8], vertical_alignment="center")
        note_col.markdown(MANUAL_MODE_NOTE)
        back_col.button("Volver a datos de Amazon Ads", key=picker_key(key_prefix, "back_to_api"),
                        type="tertiary", icon=":material/arrow_back:",
                        on_click=search_term_source._set_manual_mode, args=(key_prefix, False))
        return _render_file_input(key_prefix, hint="")


def _render_file_input(key_prefix: str, *, hint: str) -> CampaignInput | None:
    uploaded = st.file_uploader(UPLOAD_LABEL, type=["xlsx", "csv"], key=picker_key(key_prefix, "file"))
    if hint:
        st.caption(hint)
    if uploaded is None:
        return None
    try:
        frame = _read_uploaded_file(uploaded.getvalue(), uploaded.name)
    except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, OSError) as exc:
        log.warning("campaign file %s could not be read: %s", uploaded.name, exc)
        st.error(UNREADABLE_FILE_MESSAGE)
        return None
    return CampaignInput(frame=frame, currency_code="")


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _read_uploaded_file(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    return read_campaign_file(file_bytes, file_name)


@st.cache_data(ttl=STATUS_TTL_SECONDS, show_spinner=False)
def _load_campaign_sync(profile_id: str) -> tuple[SyncJob | None, SyncJob | None]:
    """(latest campaign job, last one that completed) for the profile."""
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    store = SyncJobStore(rest)
    try:
        return (store.latest_for_profile(profile_id, CAMPAIGNS_KIND),
                store.latest_completed_for_profile(profile_id, CAMPAIGNS_KIND))
    except (requests.RequestException, ValueError) as exc:
        raise ReportReadError(_error_message(exc, "leer el estado de las campañas de Amazon Ads")) from exc


@st.cache_data(ttl=STATUS_TTL_SECONDS, show_spinner=False)
def _load_products_sync(profile_id: str) -> datetime | None:
    """When the last SB or SD campaign request finished, None if none did."""
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    try:
        job = SyncJobStore(rest).latest_completed_of_kinds(profile_id, PRODUCT_CAMPAIGN_KINDS)
    except (requests.RequestException, ValueError) as exc:
        raise ReportReadError(_error_message(exc, "leer el estado de las campañas SB y SD")) from exc
    return job.finished_at if job is not None else None


# synced_at is part of the key, as with SP: the analysis IA looks its payload up by what these campaigns say, so
# a finished SB or SD request has to reach the page as soon as it reaches the worker.
@st.cache_data(ttl=PRODUCTS_TTL_SECONDS, max_entries=16, show_spinner="Cargando campañas SB y SD, y targets…")
def _load_products(profile_id: str, start: date, end: date,
                   synced_at: datetime | None) -> tuple[ProductCampaigns | None, IdleTargets | None]:
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    provider = ProductProvider(rest)
    return provider.campaigns(profile_id, start, end), provider.idle_targets(profile_id, start, end)


@st.cache_data(ttl=CAMPAIGNS_TTL_SECONDS, max_entries=16, show_spinner="Cargando campañas de Amazon Ads…")
def _load_campaigns(option: ProfileOption, start: date, end: date, synced_at: datetime | None) -> CampaignSource:
    # synced_at is part of the key: each nightly sync rewrites past days too, so a new sync means a new read.
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    return CampaignProvider(rest).campaigns(option, start, end)

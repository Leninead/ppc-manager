"""PPC Insights' campaigns: the SP listing of the account the Search Term picker chose, or a Campaign CSV by hand.

With Amazon Ads data the block reads the listing of that same account (core/ppc_insights/campaign_coverage.py), so
the AM never picks the account twice. With a report uploaded by hand, or when the AM asks, the Campaign CSV uploader
of always. The account's listing is read in both cases: the stored AI analysis reads it, never a file.
"""
from __future__ import annotations

import hashlib
import html
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

import streamlit as st

from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.date_labels import day_phrase
from core.ppc_insights.campaign_coverage import CampaignListing, ListedCampaigns, read_campaign_listing
from core.search_term.frame import SOURCE_FILE, SearchTermSource
from core.ui import palette
from modules.pages import search_term_source
from modules.pages.keyword_listing_source import listing_moment, profile_option
from modules.pages.search_term_source import ASK_AN_ADMIN, count_label, picker_key

log = logging.getLogger(__name__)

KEY_PREFIX = "insights_campaigns"
UPLOADER_KEY = "insights_camp"
UPLOAD_LABEL = "Campaign CSV (opcional)"
LISTING_TTL_SECONDS = 15 * 60
BLOCK_TITLE = "Campañas de la cuenta"
BLOCK_TAG = "Misma cuenta del Search Term Report"
FILE_MODE_NOTE = "Estás usando un Campaign CSV subido a mano. No se guarda ni se mezcla con los datos de Amazon Ads."
FILE_FALLBACK_HINT = "Mientras tanto podés subir el Campaign CSV a mano."
NO_DATABASE_MESSAGE = "No hay base de datos configurada para leer las campañas de la cuenta."
ACCOUNT_NOT_LISTED_MESSAGE = "No se pudo leer la cuenta elegida en la lista de cuentas de Amazon Ads."
UNREADABLE_REASON = "No se pudieron leer las campañas de la cuenta."
NO_FILE_REASON = "No se subió el Campaign CSV."
COUNTS_NOTE = ("Cuentan las campañas y ad groups habilitados con un anuncio habilitado; el ASIN, por lo que anuncian "
               "o por el nombre de la campaña.")


@dataclass(frozen=True, eq=False)
class CampaignsInput:
    """The campaigns PPC Insights reads: the account's listing, a Campaign CSV uploaded by hand, or why neither."""

    # The account's listing: what the stored AI analysis reads, even while the cards read a file.
    listing: ListedCampaigns | None = None
    upload: object | None = None
    missing_reason: str = NO_FILE_REASON

    @property
    def signature(self) -> str:
        """What the insights on screen depend on: the file's bytes, or when the listing was taken."""
        if self.upload is not None:
            return "file:" + hashlib.sha256(self.upload.getvalue()).hexdigest()[:16]
        if self.listing is not None and self.listing.listed_at is not None:
            return f"listing:{self.listing.listed_at.isoformat()}"
        return ""


def render_campaigns_block(source: SearchTermSource) -> CampaignsInput:
    """The block under the picker for Amazon Ads data; a report uploaded by hand has no account to read."""
    if source.source == SOURCE_FILE or not source.profile_id or source.window_end is None:
        raise ValueError("the campaigns block reads the account of an Amazon Ads source")
    with st.container(border=True, key=picker_key(KEY_PREFIX, "card")):
        header = st.empty()
        read, error = _read_listing(source.profile_id, source.window_end)
        if st.session_state.get(picker_key(KEY_PREFIX, "manual")):
            header.markdown(_header_html("idle", "Campaign CSV a mano"), unsafe_allow_html=True)
            return _render_file_mode(read.campaigns if read is not None else None)
        if read is None:
            header.markdown(_header_html("err", "No se pudo leer"), unsafe_allow_html=True)
            st.error(f"{error} {ASK_AN_ADMIN}")
            return _render_file_fallback(UNREADABLE_REASON)
        if read.campaigns is None:
            header.markdown(_header_html("err" if read.refused else "warn",
                                         "Sin permiso" if read.refused else "Sin listar"), unsafe_allow_html=True)
            st.caption(f"{read.missing_reason} {FILE_FALLBACK_HINT}")
            return _render_file_fallback(read.missing_reason)

        now = datetime.now(timezone.utc)
        header.markdown(_header_html("ok", f"Listadas {listing_moment(read.campaigns.listed_at, now, day_phrase)}"),
                        unsafe_allow_html=True)
        info_col, action_col = st.columns([4.2, 3.8], vertical_alignment="center")
        info_col.markdown(search_term_source._muted_line_html(_counts(read.campaigns)), unsafe_allow_html=True)
        with action_col:
            _render_upload_action()
        st.caption(COUNTS_NOTE)
        return CampaignsInput(listing=read.campaigns)


def file_campaigns(upload) -> CampaignsInput:
    """A Campaign CSV uploaded next to a report uploaded by hand: there is no account whose listing to read."""
    return CampaignsInput(upload=upload)


@st.cache_data(ttl=LISTING_TTL_SECONDS, max_entries=8, show_spinner="Leyendo las campañas de la cuenta…")
def load_campaign_listing(option: ProfileOption, day: date) -> CampaignListing:
    """Raises ReportReadError when the campaigns cannot be read."""
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    return read_campaign_listing(rest, option, day)


def _read_listing(profile_id: str, day: date) -> tuple[CampaignListing | None, str]:
    """The account's listing, or None and what to tell the AM when it cannot be read."""
    option = profile_option(profile_id)
    if option is None:
        return None, ACCOUNT_NOT_LISTED_MESSAGE
    try:
        return load_campaign_listing(option, day), ""
    except ReportReadError as exc:
        log.warning("ppc insights: campaign listing unreadable for profile %s: %s", profile_id, exc)
        return None, str(exc)


def _counts(campaigns: ListedCampaigns) -> list[str]:
    return [f"{count_label(campaigns.campaign_count)} campañas SP habilitadas",
            f"{count_label(len(campaigns.ad_groups))} ad groups con anuncios"]


def _header_html(kind: str, label: str) -> str:
    return palette.band_header_html(title=BLOCK_TITLE, tag=BLOCK_TAG,
                                    right=palette.status_pill_html(kind, html.escape(label)))


def _render_upload_action() -> None:
    actions_key = picker_key(KEY_PREFIX, "actions")
    st.markdown(search_term_source._actions_css(actions_key), unsafe_allow_html=True)
    with st.container(key=actions_key):
        st.button("Subir Campaign CSV a mano", key=picker_key(KEY_PREFIX, "upload_manual"), type="secondary",
                  icon=":material/upload:", on_click=search_term_source._set_manual_mode, args=(KEY_PREFIX, True))


def _render_file_fallback(missing_reason: str) -> CampaignsInput:
    """No listing to read: the Campaign CSV uploader right away, as the fallback."""
    upload = st.file_uploader(UPLOAD_LABEL, type=["csv"], key=UPLOADER_KEY)
    return CampaignsInput(upload=upload, missing_reason=missing_reason)


def _render_file_mode(listing: ListedCampaigns | None) -> CampaignsInput:
    note_col, back_col = st.columns([4.2, 1.8], vertical_alignment="center")
    note_col.markdown(FILE_MODE_NOTE)
    back_col.button("Volver a datos de Amazon Ads", key=picker_key(KEY_PREFIX, "back_to_api"), type="tertiary",
                    icon=":material/arrow_back:", on_click=search_term_source._set_manual_mode,
                    args=(KEY_PREFIX, False))
    upload = st.file_uploader(UPLOAD_LABEL, type=["csv"], key=UPLOADER_KEY)
    return CampaignsInput(listing=listing, upload=upload)

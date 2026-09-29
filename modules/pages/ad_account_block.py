"""The Amazon Ads account behind a Business Report: the block that picks it, and that account's ads over the report's days.

The Business Report does not say whose it is, so the block never picks an account on its own. The ads come from the
account's synced campaign reports (Sponsored Products, Brands and Display, as Campaign Manager counts them), over the
report's days that the campaign sync keeps. PPC Forecast, Account Pulse and Weekly Client Report mount it.
"""
import html
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import partial
from typing import Any

import pandas as pd
import streamlit as st

from core.amazon_ads import campaign_totals
from core.amazon_ads.campaign_provider import campaign_sync_view
from core.amazon_ads.campaign_totals import ProductSeries
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.sync_planner import PROFILE_NEEDS_REAUTH
from core.business_report.paid_split import PaidSplit, covered_window, paid_split
from core.currency_format import money
from core.date_labels import date_range_label, short_date
from core.ui import palette
from modules.pages import campaign_source, search_term_source
from modules.pages.search_term_source import (
    NEEDS_REAUTH_MESSAGE,
    STATE_FIRST_LOAD_FAILED,
    country_labels,
    group_by_label,
    picker_key,
    source_state,
)

log = logging.getLogger(__name__)

AD_TOTALS_TTL_SECONDS = 60 * 60
BLOCK_TAG = "Reportes de campañas de Amazon Ads"
ACCOUNT_PLACEHOLDER = "Elegí la cuenta del BR"
NO_CAMPAIGN_DATA_NOTE = "Todavía no hay métricas de campañas de esta cuenta: se sincronizan una vez por día."
FIRST_LOAD_FAILED_NOTE = ("La primera carga de campañas de esta cuenta no se pudo completar. Si sigue así, avisale a "
                          "un admin.")
NO_DATABASE_MESSAGE = "No hay base de datos configurada para leer las campañas de Amazon Ads."
ADS_EXCEED_BR_WARNING = ("Las ventas de ads ({ad_sales}) superan las del BR ({br_sales}) en los mismos días: revisá "
                         "que la cuenta y el país sean los del BR.")

# Why there are no ads figures: shown on the page and sent to the AI as is.
MISSING_NO_ACCOUNTS = "no hay cuentas de Amazon Ads conectadas"
MISSING_NOT_CHOSEN = "no se eligió la cuenta de Amazon Ads del BR"
MISSING_NOT_SYNCED = "la cuenta todavía no tiene campañas sincronizadas"
MISSING_UNREADABLE = "no se pudieron leer las campañas de la cuenta"
MISSING_NO_SHARED_DAYS = ("el BR va del {first} al {last} y la cuenta tiene campañas sincronizadas del {synced_from} "
                          "al {synced_through}: no hay días en común")


@dataclass(frozen=True)
class AdAccountTexts:
    """What the block says in one module: its title, and what the module gets or loses with the account."""

    title: str
    no_accounts: str
    choose_account: str
    first_load: str
    unreadable: str
    without_ads: str  # opens the line that says why there are no ads figures: "Sin desglose: …"


@dataclass(frozen=True)
class AdAccountChoice:
    """The block's outcome: the chosen profile as the campaign sync sees it, or why there is none."""

    profile: ProfileOption | None = None
    info_line: Any = None  # the block's last line, filled in once the Business Report's days are known
    no_ads_reason: str = ""


@dataclass(frozen=True, eq=False)
class AccountAds:
    """What the chosen account's campaign reports say about the Business Report's days, or why they say nothing."""

    account: str = ""
    profile_id: str = ""
    country_code: str = ""
    currency_code: str = ""
    series: ProductSeries | None = None
    split: PaidSplit | None = None
    campaigns: pd.DataFrame | None = None  # one row per campaign with activity, read only when asked for
    no_ads_reason: str = ""


def render_ad_account_block(key_prefix: str, texts: AdAccountTexts) -> AdAccountChoice:
    """Mounts the block; returns the chosen profile as the campaign sync sees it, or why there is none."""
    search_term_source._keep_choices(key_prefix)
    profiles = search_term_source._available_profiles()
    if not profiles:
        st.caption(texts.no_accounts)
        return AdAccountChoice(no_ads_reason=MISSING_NO_ACCOUNTS)

    groups = group_by_label(profiles)
    card_key = picker_key(key_prefix, "card")
    st.markdown(search_term_source._card_css(card_key), unsafe_allow_html=True)
    with st.container(border=True, key=card_key):
        header = st.empty()
        account_col, country_col = st.columns([2.2, 1.3])
        account = _choose_account(account_col, key_prefix, list(groups))
        if account is None:
            header.markdown(_block_header(texts, "idle", "Sin cuenta elegida"), unsafe_allow_html=True)
            st.caption(texts.choose_account)
            return AdAccountChoice(no_ads_reason=MISSING_NOT_CHOSEN)

        countries = country_labels(groups[account])
        profile_id = search_term_source._resolve_choice(key_prefix, "profile", list(countries), fallback=None)
        country_col.segmented_control("País", options=list(countries), format_func=countries.get,
                                      key=picker_key(key_prefix, "profile"))
        option = next(profile for profile in groups[account] if profile.profile_id == profile_id)
        now = datetime.now(timezone.utc)
        try:
            latest_job, completed = campaign_source._load_campaign_sync(option.profile_id)
        except ReportReadError as exc:
            log.warning("%s: campaign sync unreadable for profile %s: %s", key_prefix, option.profile_id, exc)
            header.markdown(_block_header(texts, "err", "No se pudo leer"), unsafe_allow_html=True)
            st.error(f"{exc} {texts.unreadable}")
            return AdAccountChoice(no_ads_reason=MISSING_UNREADABLE)

        synced = campaign_sync_view(option, completed)
        header.markdown(_block_header(texts, *campaign_source.campaign_pill(synced, latest_job, now)),
                        unsafe_allow_html=True)
        if option.status == PROFILE_NEEDS_REAUTH:
            st.warning(NEEDS_REAUTH_MESSAGE)
        if synced.data_through is None:
            if latest_job is None:
                st.info(NO_CAMPAIGN_DATA_NOTE)
            elif source_state(synced, latest_job, now) == STATE_FIRST_LOAD_FAILED:
                st.error(FIRST_LOAD_FAILED_NOTE)
            else:
                st.info(texts.first_load)
            return AdAccountChoice(no_ads_reason=MISSING_NOT_SYNCED)
        info_line = st.empty()
        info_line.markdown(_synced_line(synced), unsafe_allow_html=True)
    return AdAccountChoice(profile=synced, info_line=info_line)


def read_account_ads(choice: AdAccountChoice, history: pd.DataFrame, texts: AdAccountTexts, *,
                     with_campaigns: bool = False) -> AccountAds:
    """The chosen account's ads over the Business Report's days (`history`: one row per day with `_date` and
    `_sales`), or why there are none; `with_campaigns` also reads them per campaign over the same days."""
    profile = choice.profile
    if profile is None:
        return AccountAds(no_ads_reason=choice.no_ads_reason)
    identity = dict(account=account_label(profile), profile_id=profile.profile_id, country_code=profile.country_code)
    first, last = history["_date"].min().date(), history["_date"].max().date()
    window = covered_window(first, last, profile.data_from, profile.data_through)
    if window is None:
        reason = MISSING_NO_SHARED_DAYS.format(first=short_date(first), last=short_date(last),
                                                synced_from=short_date(profile.data_from),
                                                synced_through=short_date(profile.data_through))
        choice.info_line.caption(f"{texts.without_ads}: {reason}.")
        return AccountAds(**identity, currency_code=profile.currency_code, no_ads_reason=reason)
    try:
        series = load_daily_totals(profile, *window)
        campaigns = load_campaign_totals(profile, *window) if with_campaigns else None
    except ReportReadError as exc:
        log.warning("Ad totals unreadable for profile %s: %s", profile.profile_id, exc)
        choice.info_line.error(f"{exc} {texts.unreadable}")
        return AccountAds(**identity, currency_code=profile.currency_code, no_ads_reason=MISSING_UNREADABLE)
    split = paid_split(history, series)
    choice.info_line.markdown(_covered_line(split), unsafe_allow_html=True)
    return AccountAds(**identity, currency_code=split.currency_code, series=series, split=split, campaigns=campaigns)


def account_label(option: ProfileOption) -> str:
    return f"{option.label} · {option.country_code}" if option.country_code else option.label


def ads_exceed_br_warning(split: PaidSplit) -> str:
    """Said when the account's ad sales exceed the report's on the same days: the account is likely not the report's."""
    show = partial(money, currency_code=split.currency_code)
    # Streamlit renders the text between two bare $ as LaTeX.
    return ADS_EXCEED_BR_WARNING.format(ad_sales=show(split.ad_sales).replace("$", "\\$"),
                                        br_sales=show(split.br_sales).replace("$", "\\$"))


# The profile carries its last campaign sync: a new sync is a new read, never an old one served again.
@st.cache_data(ttl=AD_TOTALS_TTL_SECONDS, max_entries=16, show_spinner="Leyendo las ventas de ads de la cuenta…")
def load_daily_totals(profile: ProfileOption, start: date, end: date) -> ProductSeries:
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    return campaign_totals.daily_totals(rest, profile, start, end)


@st.cache_data(ttl=AD_TOTALS_TTL_SECONDS, max_entries=16, show_spinner="Leyendo las campañas de la cuenta…")
def load_campaign_totals(profile: ProfileOption, start: date, end: date) -> pd.DataFrame:
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    return campaign_totals.window_totals(rest, profile, start, end)


def _choose_account(column, key_prefix: str, accounts: list[str]) -> str | None:
    """The chosen account, never a default one: the Business Report does not say whose it is."""
    key = picker_key(key_prefix, "account")
    if st.session_state.get(key) not in accounts:
        st.session_state[key] = None
    return column.selectbox("Cuenta", accounts, index=None, placeholder=ACCOUNT_PLACEHOLDER, key=key)


def _block_header(texts: AdAccountTexts, kind: str, label: str) -> str:
    return palette.band_header_html(title=texts.title, tag=BLOCK_TAG,
                                    right=palette.status_pill_html(kind, html.escape(label)))


def _synced_line(profile: ProfileOption) -> str:
    parts = [html.escape(f"Campañas sincronizadas: {date_range_label(profile.data_from, profile.data_through)}")]
    if profile.currency_code:
        parts.append(palette.marketplace_chip_html(html.escape(profile.currency_code)))
    return search_term_source._muted_line_html(parts)


def _covered_line(split: PaidSplit) -> str:
    parts = [html.escape(date_range_label(split.start, split.end)),
             html.escape(f"{split.covered_days} de {split.history_days} días del BR con datos de ads")]
    if split.currency_code:
        parts.append(palette.marketplace_chip_html(html.escape(split.currency_code)))
    parts.append(html.escape(" · ".join(split.products) if split.products else "Sin campañas con actividad"))
    return search_term_source._muted_line_html(parts)

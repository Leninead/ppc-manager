"""An account's Sponsored Products keyword listing for the pages: read at most once per quarter hour, dated for screen.

The listing is the daily snapshot of the SP campaigns, ad groups and keywords (core/amazon_ads/structure_listing.py);
a search term report only carries the keywords that got clicks in its window.
"""
from datetime import date, datetime

import streamlit as st

from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.structure_listing import KeywordListing, read_keyword_listing
from modules.pages import search_term_source
from modules.pages.search_term_source import DISPLAY_TIMEZONE

KEYWORD_LISTING_TTL_SECONDS = 15 * 60
NO_DATABASE_MESSAGE = "No hay base de datos configurada para leer el listado de Sponsored Products."


@st.cache_data(ttl=KEYWORD_LISTING_TTL_SECONDS, show_spinner="Leyendo el listado de Sponsored Products de la cuenta…")
def load_keyword_listing(option: ProfileOption, day: date) -> KeywordListing:
    """The account's latest SP campaigns, ad groups and keywords; raises ReportReadError when they cannot be read."""
    rest = search_term_source._open_rest()
    if rest is None:
        raise ReportReadError(NO_DATABASE_MESSAGE)
    return read_keyword_listing(rest, option, day)


def profile_option(profile_id: str) -> ProfileOption | None:
    """The connected profile behind a search term source, or None once it is no longer listed."""
    return next((option for option in search_term_source._available_profiles() if option.profile_id == profile_id),
                None)


def listing_moment(listed_at: datetime, now: datetime, phrase) -> str:
    """The listing's day as `phrase` words it (day_phrase, data_of_day_phrase) and its time, in the team's timezone."""
    local = listed_at.astimezone(DISPLAY_TIMEZONE)
    return f"{phrase(local.date(), now.astimezone(DISPLAY_TIMEZONE).date())} {local:%H:%M}"

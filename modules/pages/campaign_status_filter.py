"""The «Estado de campaña» filter the pages put over their campaign lists: Campaign Manager's Active status.

Its texts are the `campaign_status.*` keys of core/ui/i18n.py, so it follows the language toggle on every page.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.amazon_ads.campaign_status import StatusFilter, filter_by_status
from core.search_term.frame import SOURCE_FILE, SearchTermSource
from core.ui import i18n

DEFAULT_STATUS = StatusFilter.ENABLED
SEARCH_TERM_STATE_COLUMN = "_campaign_status"


def filter_label() -> str:
    return i18n.t("campaign_status.label")


def status_label(status: StatusFilter) -> str:
    return i18n.t(f"campaign_status.option.{status.value}")


def no_campaigns_text() -> str:
    return i18n.t("campaign_status.no_campaigns")


def render_campaign_status_filter(key: str, *, unavailable_reason: str = "") -> StatusFilter | None:
    """Draws the filter and returns the chosen status. With `unavailable_reason` it is drawn disabled, says why,
    and returns None: the page keeps every campaign.

    The choice is also kept in `<key>_choice`, so it survives a run where the page does not draw the filter and
    a switch of language."""
    if unavailable_reason:
        st.selectbox(filter_label(), [status_label(StatusFilter.ALL)], key=f"{key}_unavailable", disabled=True)
        st.caption(unavailable_reason)
        return None
    choice_key = f"{key}_choice"
    # Streamlit 1.43 tells selectboxes apart by label and options too: a relabeled one starts from what is stored here.
    st.session_state[key] = StatusFilter(
        st.session_state.get(key) or st.session_state.get(choice_key) or DEFAULT_STATUS)
    selected = StatusFilter(st.selectbox(
        filter_label(), list(StatusFilter), format_func=status_label, key=key,
        help=i18n.t("campaign_status.help", enabled=status_label(StatusFilter.ENABLED))))
    st.session_state[choice_key] = selected
    return selected


def filter_search_terms_by_status(source: SearchTermSource, frame: pd.DataFrame, *, key: str) -> pd.DataFrame:
    """The search terms of `frame` whose campaign the chosen status keeps. A hand-uploaded report carries no
    campaign state, so its terms all stay."""
    if source.source == SOURCE_FILE:
        render_campaign_status_filter(key, unavailable_reason=i18n.t("campaign_status.unavailable.hand_upload"))
        return frame
    return filter_by_status(frame, SEARCH_TERM_STATE_COLUMN, render_campaign_status_filter(key))

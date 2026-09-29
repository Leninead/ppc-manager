"""The accounts the chat can read and the analyses saved for each: what a conversation opens with.

To place itself before answering, the chat called list_accounts and list_analyses — up to 13,000 characters a page,
several pages a question — and used a few fields of each account: its name, its currency, until which day it has
data and which modules have a saved analysis. Those fields alone go here, once, with the turn that opens a
conversation; the tools still hold everything else.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

import requests
import streamlit as st

from core.ai_analysis.store import CHAT_READ_MODULES, AiAnalysisStore, SavedWindow
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, ReportReadError, account_labels
from core.integrations.store import _Rest, _rest_credentials

log = logging.getLogger(__name__)

TITLE = "Cuentas de Amazon Ads de la agencia y sus análisis guardados"
HEADER = ("Una línea por cuenta sincronizada: el nombre que toma `account`, su profile_id, su moneda, hasta qué día "
          "tiene datos y la ventana del último análisis guardado de cada módulo, el que baja `get_analysis`. Es la "
          "lista completa: para saber qué cuentas hay o cuáles tienen análisis no hace falta list_accounts ni "
          "list_analyses.")
_CACHE_TTL_S = 300


def directory_document() -> dict | None:
    """The directory as a conversation document, or None when the accounts cannot be read."""
    lines = _read_directory()
    return {"title": TITLE, "content": "\n".join([HEADER, *lines])} if lines else None


def directory_lines(profiles: Iterable[ProfileOption], saved: Iterable[SavedWindow]) -> list[str]:
    """One line per account with data, by name: `name | profile_id | currency | data through | analyses`."""
    synced = [profile for profile in profiles if profile.data_through is not None]
    labels = account_labels(synced)
    windows: dict[str, list[SavedWindow]] = {}
    for window in saved:
        windows.setdefault(window.subject_id, []).append(window)
    return [f"{labels[profile.profile_id]} | {profile.profile_id} | {profile.currency_code} | datos hasta "
            f"{profile.data_through.isoformat()} | análisis: {_analyses(windows.get(profile.profile_id, []))}"
            for profile in sorted(synced, key=lambda profile: labels[profile.profile_id])]


@st.cache_data(ttl=_CACHE_TTL_S, show_spinner=False)
def _read_directory() -> list[str]:
    credentials = _rest_credentials()
    if credentials is None:
        return []
    rest = _Rest(*credentials)
    try:
        profiles = ReportProvider(rest).profiles()
        saved = AiAnalysisStore(rest).newest_windows(
            CHAT_READ_MODULES, [profile.profile_id for profile in profiles if profile.data_through is not None])
    except (ReportReadError, requests.RequestException) as exc:
        log.warning("account directory not read, the chat opens without it: %s", exc)
        return []
    return directory_lines(profiles, saved)


def _analyses(windows: list[SavedWindow]) -> str:
    if not windows:
        return "ninguno"
    return ", ".join(f"{window.module} {_span(window)}" for window in sorted(windows, key=lambda w: w.module))


def _span(window: SavedWindow) -> str:
    if window.window_start and window.window_end:
        return f"{window.window_start.isoformat()} a {window.window_end.isoformat()}"
    return "sin ventana"

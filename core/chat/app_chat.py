"""The app's one AI chat: what each page shares with it, and the bubble mounted on every page.

A page shares the analysis it shows and withdraws it when it has none. What a page
shared stays available while the AM moves to other pages; `mount_app_chat`, called
once at the end of app.py, opens the provider session with every shared analysis. The
other accounts are not pasted: the model reads them through the app's MCP server.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import partial

import streamlit as st

from ai import config as ai_config
from ai import runtime as ai_runtime
from core import navigation
from core.chat import ads_scope, turns
from core.chat.panel import ChatTurn, floating_chat
from core.ui import i18n

log = logging.getLogger(__name__)

CHAT_ID = "app"
AGENT = "orchestrator"
_STATE_KEY = "app_chat_modules"
_REGION_KEY = "app_chat_session_country"
_CONVERSATION_KEY = "app_chat_conversation_id"


class AnalysisState(str, Enum):  # str-valued: entries survive a module reload in session_state
    CURRENT = "current"
    OUTDATED = "outdated"
    RUNNING = "running"
    FAILED = "failed"
    MISSING = "missing"


@dataclass(frozen=True)
class ChatAnalysis:
    """One module's analysis as the chat reads it."""

    module: str
    key: str
    subject: str
    documents: tuple[dict, ...]
    annotate: Callable[[str], str] | None = None
    country_code: str = ""
    profile_id: str = ""


@dataclass(frozen=True)
class _ModuleEntry:
    state: AnalysisState
    page: str
    analysis: ChatAnalysis | None = None
    digest: str = ""
    finish: Callable | None = None


def share_analysis(analysis: ChatAnalysis, state: AnalysisState = AnalysisState.CURRENT) -> None:
    """A state other than CURRENT says the documents are not an analysis of what the page shows."""
    _entries()[analysis.module] = _ModuleEntry(state, _current_page(), analysis)


def keep_current(module: str, key: str) -> bool:
    """True when that analysis is already shared, which marks it current again."""
    entry = _entries().get(module)
    if entry is None or entry.analysis is None or entry.analysis.key != key:
        return False
    if entry.state != AnalysisState.CURRENT:
        _entries()[module] = _ModuleEntry(AnalysisState.CURRENT, entry.page, entry.analysis)
    return True


def mark_outdated(module: str, key: str) -> None:
    """The page still shows that analysis, but its parameters changed since."""
    entry = _entries().get(module)
    if entry is not None and entry.analysis is not None and entry.analysis.key == key:
        _entries()[module] = _ModuleEntry(AnalysisState.OUTDATED, entry.page, entry.analysis)
    else:
        withdraw_analysis(module)


def report_running(module: str, digest: str = "", finish: Callable | None = None) -> None:
    """An analysis still being generated. With the digest of one in this process, `finish(analysis)`
    builds what the chat reads once it is done; without it the state stands until the page reports again."""
    _entries()[module] = _ModuleEntry(AnalysisState.RUNNING, _current_page(), digest=digest, finish=finish)


def report_failed(module: str) -> None:
    _entries()[module] = _ModuleEntry(AnalysisState.FAILED, _current_page())


def withdraw_analysis(module: str) -> None:
    _entries().pop(module, None)


def shared_analyses(entries: dict) -> list[ChatAnalysis]:
    return [entry.analysis for entry in entries.values() if entry.analysis is not None]


def session_key(analyses: list[ChatAnalysis]) -> str:
    """Changes when the AM's own analyses do, and only then: a new key opens a new provider session.

    The stored analyses of every account stay out: one of them changes every time any account gets a
    new analysis, which would restart everybody's conversation during the day.
    """
    return "|".join(sorted(analysis.key for analysis in analyses))


def session_documents(analyses: list[ChatAnalysis]) -> list[dict]:
    return [document for analysis in analyses for document in analysis.documents]


def turn_note(page: str, entries: dict) -> str:
    """App state the model reads ahead of every question; the AM never sees it."""
    lines = [f"el AM tiene abierta la pantalla «{navigation.visible_label(page)}»."]
    if not entries:
        lines.append("No hay análisis abiertos en esta sesión.")
    for entry in entries.values():
        lines.append(_state_line(entry, page))
    return "[Nota de la app, no la cites: " + " ".join(lines) + "]"


def mount_app_chat(page: str, username: str) -> None:
    """The bubble, on every page. Nothing is read or sent until the AM asks something."""
    if not ai_config.AI_ENABLED:
        return
    floating_chat(chat_id=CHAT_ID, agent=AGENT, lang=i18n.current_lang(),
                  session_key=chat_session_key, turn=partial(chat_turn, page),
                  on_turn_finished=partial(record_turn, page, username))


def record_turn(page: str, username: str, question: str, reply: ai_runtime.ChatReply | None,
                shown: str) -> None:
    """Keeps a finished turn in the database; one that failed keeps the error the AM read."""
    analysis = _ads_analysis_on_page(page, _entries())
    context = dict(conversation_id=_conversation_id(), username=username, page=page, question=question,
                   ads_profile_id=analysis.profile_id if analysis else None,
                   ads_account=analysis.subject if analysis else None)
    if reply is None:
        turn = turns.ChatTurnRecord(**context, answer=None, error=shown)
    else:
        turn = turns.ChatTurnRecord(**context, answer=shown, error=None, tools=reply.tool_calls,
                                    model=reply.model, cost_usd=reply.cost_usd)
    turns.record(turn)


def chat_session_key() -> str:
    """Runs on every render of every page: only the analyses this session shares, no reads."""
    _finish_running_analyses()
    return session_key(shared_analyses(_entries()))


def chat_turn(page: str) -> ChatTurn:
    """What a question on this page is sent with, built when the AM sends it."""
    _finish_running_analyses()
    entries = dict(_entries())
    analyses = shared_analyses(entries)
    return ChatTurn(
        documents=session_documents(analyses),
        note=turn_note(page, entries),
        ads_scope=ads_scope.request_scope(
            _session_country_hint(session_key(analyses), page, entries)),
        annotate=_annotator(analyses),
    )


def _entries() -> dict[str, _ModuleEntry]:
    return st.session_state.setdefault(_STATE_KEY, {})


def _current_page() -> str:
    return st.session_state.get("selected_page") or navigation.HOME


def _conversation_id() -> str:
    """One per browser session, as long as the thread the AM sees."""
    return st.session_state.setdefault(_CONVERSATION_KEY, str(uuid.uuid4()))


def _ads_analysis_on_page(page: str, entries: dict) -> ChatAnalysis | None:
    """The analysis of an Amazon Ads account that the page the AM asked from has loaded."""
    return next((entry.analysis for entry in entries.values()
                 if entry.page == page and entry.analysis is not None and entry.analysis.profile_id), None)


def _finish_running_analyses() -> None:
    """An analysis the AM left running on its page is read from its own digest, wherever the AM is now."""
    for module, entry in list(_entries().items()):
        if entry.state != AnalysisState.RUNNING or not entry.digest:
            continue
        analysis = ai_runtime.get(module, entry.digest)
        if analysis is None or analysis.running:
            continue
        if analysis.done and entry.finish is not None:
            _entries()[module] = _ModuleEntry(AnalysisState.CURRENT, entry.page, entry.finish(analysis))
        else:
            _entries()[module] = _ModuleEntry(AnalysisState.FAILED, entry.page)


def _state_line(entry: _ModuleEntry, page: str) -> str:
    module = navigation.visible_label(entry.page)
    subject = f" ({entry.analysis.subject})" if entry.analysis is not None and entry.analysis.subject else ""
    earlier = " En los documentos sólo hay análisis anteriores." if entry.analysis is not None else ""
    if entry.state == AnalysisState.CURRENT:
        return f"{module}{subject}: análisis disponible."
    if entry.state == AnalysisState.OUTDATED:
        return (f"{module}{subject}: el análisis que se ve corresponde a parámetros anteriores "
                f"a los que el AM tiene cargados.")
    if entry.state == AnalysisState.RUNNING:
        if entry.digest or entry.page == page:
            return f"{module}{subject}: el análisis de lo que se ve se está generando.{earlier}"
        return (f"{module}{subject}: cuando el AM dejó esa pantalla, el análisis se estaba generando; "
                f"puede haber terminado.{earlier}")
    if entry.state == AnalysisState.FAILED:
        return f"{module}{subject}: el análisis de lo que se ve falló.{earlier}"
    return f"{module}{subject}: no hay un análisis de lo que se ve.{earlier}"


def _annotator(analyses: list[ChatAnalysis]) -> Callable[[str], str]:
    annotators = [analysis.annotate for analysis in analyses if analysis.annotate is not None]

    def annotate(text: str) -> str:
        for apply in annotators:
            text = apply(text)
        return text

    return annotate


def _session_country_hint(key: str, page: str, entries: dict) -> str | None:
    """Chosen when a session opens and kept for its life: a region change mid-conversation loses its accounts."""
    kept = st.session_state.get(_REGION_KEY)
    if kept is not None and kept[0] == key:
        return kept[1]
    hint = _country_hint(page, entries)
    st.session_state[_REGION_KEY] = (key, hint)
    return hint


def _country_hint(page: str, entries: dict) -> str | None:
    """The marketplace of the analysis on this page, else of the first shared analysis that has one."""
    with_country = [entry for entry in entries.values()
                    if entry.analysis is not None and entry.analysis.country_code]
    on_page = [entry for entry in with_country if entry.page == page]
    chosen = (on_page or with_country or [None])[0]
    return chosen.analysis.country_code if chosen is not None else None

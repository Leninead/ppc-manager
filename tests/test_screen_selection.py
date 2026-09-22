"""What the chat's turn note says about the AM's selections (core/chat/screen_selection.py and app_chat)."""
import types
from datetime import date

import pytest

from core.chat import app_chat
from core.chat.screen_selection import ScreenSelection, ToolCall, selection_text, selections_note

FUNNEL = ScreenSelection(
    module="Análisis de Funnel", account="Luna Kids · US", source="Amazon Ads",
    window_start=date(2026, 9, 14), window_end=date(2026, 9, 20),
    values=(("mínimo de órdenes para harvest", "3"), ("match type de las campañas sugeridas", "Phrase")),
    calls=(ToolCall("funnel_coverage", (("profile_id", "111"), ("date_from", "2026-09-14"),
                                         ("date_to", "2026-09-20"), ("min_orders", 3), ("match_type", "Phrase"))),))
STR = ScreenSelection(module="Search Term Report", account="Havanna · US", source="Amazon Ads",
                      window_start=date(2026, 9, 1), window_end=date(2026, 9, 30))
SQP = ScreenSelection(module="Search Query Performance", account="marca wamery", source="un archivo subido a mano",
                      notes=("El MCP no ve archivos subidos a mano.",))


def test_a_selection_reads_as_one_sentence_with_the_call_that_brings_its_figures():
    assert selection_text(FUNNEL) == (
        "«Análisis de Funnel» con Luna Kids · US, del 2026-09-14 al 2026-09-20, datos de Amazon Ads; valores en "
        "pantalla: mínimo de órdenes para harvest = 3, match type de las campañas sugeridas = Phrase; sus cifras "
        'salen de funnel_coverage(profile_id="111", date_from="2026-09-14", date_to="2026-09-20", min_orders=3, '
        'match_type="Phrase").')


def test_a_hand_uploaded_file_has_no_days_no_call_and_says_why():
    assert selection_text(SQP) == ("«Search Query Performance» con marca wamery, datos de un archivo subido a mano. "
                                   "El MCP no ve archivos subidos a mano.")


def test_the_open_page_comes_first_and_the_earlier_ones_newest_first():
    selections = {"📊 Search Term Report": STR, "🔍 Search Query Performance": SQP, "🔻 Análisis de Funnel": FUNNEL}

    lines = selections_note("🔻 Análisis de Funnel", selections, remembered=5)

    assert lines[0].startswith("Lo que tiene seleccionado en esta pantalla: «Análisis de Funnel»")
    assert lines[1].index("«Search Query Performance»") < lines[1].index("«Search Term Report»")


def test_a_page_without_a_selection_only_lists_what_was_seen_before():
    lines = selections_note("🏠 Inicio", {"📊 Search Term Report": STR}, remembered=5)

    assert lines == ["Antes miró, de lo más reciente a lo más viejo: " + selection_text(STR)]


@pytest.fixture
def session(monkeypatch):
    state = {"selected_page": "📊 Search Term Report"}
    monkeypatch.setattr(app_chat, "st", types.SimpleNamespace(session_state=state))
    return state


def test_the_chat_remembers_what_the_am_saw_on_the_pages_it_left(session):
    app_chat.share_selection(STR)
    session["selected_page"] = "🔻 Análisis de Funnel"
    app_chat.share_selection(FUNNEL)

    note = app_chat.turn_note("🔻 Análisis de Funnel", {}, session["app_chat_selections"])

    assert "Lo que tiene seleccionado en esta pantalla: «Análisis de Funnel» con Luna Kids · US" in note
    assert "Antes miró, de lo más reciente a lo más viejo: «Search Term Report» con Havanna · US" in note


def test_a_new_selection_on_the_same_page_replaces_the_old_one(session):
    app_chat.share_selection(STR)
    app_chat.share_selection(ScreenSelection(module="Search Term Report", account="Luna Kids · MX",
                                             source="Amazon Ads"))

    assert [selection.account for selection in session["app_chat_selections"].values()] == ["Luna Kids · MX"]


def test_a_page_that_shows_nothing_withdraws_only_its_own_selection(session):
    app_chat.share_selection(STR)
    session["selected_page"] = "🔻 Análisis de Funnel"
    app_chat.share_selection(FUNNEL)

    app_chat.withdraw_selection()

    assert list(session["app_chat_selections"]) == ["📊 Search Term Report"]


def test_only_the_last_pages_are_remembered(session):
    pages = [f"page {index}" for index in range(app_chat.REMEMBERED_SELECTIONS + 2)]
    for page in pages:
        session["selected_page"] = page
        app_chat.share_selection(ScreenSelection(module=page, account="x", source="Amazon Ads"))

    assert list(session["app_chat_selections"]) == pages[-app_chat.REMEMBERED_SELECTIONS:]


def test_changing_a_selection_never_restarts_the_conversation(session):
    before = app_chat.chat_session_key()
    app_chat.share_selection(STR)
    session["selected_page"] = "🔻 Análisis de Funnel"
    app_chat.share_selection(FUNNEL)

    assert app_chat.chat_session_key() == before


def test_the_question_travels_with_the_selection_on_screen_when_it_is_sent(session, monkeypatch):
    monkeypatch.setattr(app_chat.ads_scope, "request_scope", lambda country_hint=None: {})
    session["selected_page"] = "🔻 Análisis de Funnel"
    app_chat.share_selection(FUNNEL)

    turn = app_chat.chat_turn("🔻 Análisis de Funnel")

    assert 'funnel_coverage(profile_id="111"' in turn.note

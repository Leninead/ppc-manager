"""core/ai_chat - the keys that send a question from the chat panel.

The binding itself lives in the browser, so what is pinned here is the contract of what
ships: which box is bound, which keys escape, and that the form no longer advertises
Streamlit's own Ctrl+Enter.
"""
import pytest
from streamlit.testing.v1 import AppTest

from core.ai_chat import _L, _enter_sends_script

PANEL = "st-key-aichat_t_panel"

_CHAT = """
import streamlit as st
from core.ai_chat import ChatTurn, floating_chat
floating_chat(chat_id="t", agent="orchestrator", lang=st.session_state.get("lang", "es"),
              session_key=lambda: "k", turn=lambda: ChatTurn())
"""


def _chat(lang="es"):
    app = AppTest.from_string(_CHAT, default_timeout=30)
    app.session_state["lang"] = lang
    app.run()
    assert not app.exception
    return app


def _binding(app):
    """The script that ships to the browser, out of the component iframe that carries it."""
    return next(frame.srcdoc for frame in app.get("iframe") if PANEL in (frame.srcdoc or ""))


def test_enter_sends_the_question_and_shift_enter_keeps_adding_a_line():
    script = _binding(_chat())

    assert "e.key !== 'Enter' || e.shiftKey" in script
    assert '[data-testid="stFormSubmitButton"] button' in script


def test_the_binding_reaches_only_this_chats_box():
    """An unscoped selector would bind the first text area of whatever page is open."""
    app = _chat()

    assert f".{PANEL} textarea" in _binding(app)
    assert PANEL in " ".join(str(block.value) for block in app.markdown)


def test_the_form_no_longer_advertises_streamlits_english_ctrl_enter():
    assert _chat().get("form")[0].proto.form.enter_to_submit is False


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_send_button_explains_both_keys_in_the_ams_language(lang):
    assert _chat(lang).button[0].help == _L[lang]["send_hint"]


def test_the_binding_survives_the_box_being_replaced_by_the_next_turn():
    """Every answer gives the form a new text area while the component frame stays put, so a
    one-shot bind left Enter dead from the second question on."""
    assert "new MutationObserver(bind).observe(doc.body" in _enter_sends_script("aichat_t_panel")


def test_a_composing_ime_keeps_its_enter():
    assert "e.isComposing || e.keyCode === 229" in _enter_sends_script("aichat_t_panel")


def test_the_script_never_closes_its_own_tag():
    """A literal "</" inside <script> ends the block early and spills the rest as markup."""
    assert "</" not in _enter_sends_script("aichat_t_panel")

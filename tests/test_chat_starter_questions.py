"""The chat's start screen: the questions it offers by page, in the stage the thread will fill, sent on a click."""
from streamlit.testing.v1 import AppTest

from ai import runtime
from core import navigation
from core.chat import panel
from core.chat.starter_questions import LIMIT, STARTER_QUESTIONS, for_page

EVERYWHERE_ES = [question.text["es"] for question in STARTER_QUESTIONS if not question.pages]

CHAT = """
from core.chat.panel import ChatTurn, floating_chat
floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k", turn=lambda: ChatTurn(),
              starters=lambda: ["¿Qué campañas pausarías hoy?", "¿Qué search terms conviene negativizar?"])
"""


def test_every_page_a_question_names_is_a_page_of_the_app():
    named = {page for question in STARTER_QUESTIONS for page in question.pages}

    assert named <= set(navigation.all_pages())


def test_every_question_is_written_in_both_languages():
    for question in STARTER_QUESTIONS:
        assert set(question.text) == {"es", "en"}
        assert all(text.endswith("?") for text in question.text.values())


def test_the_open_page_questions_come_first_and_the_list_stays_short():
    bulk = for_page("📁 Bulk Campañas", "es", seed="conversation-1")

    assert set(bulk[:2]) == {"¿Qué campañas pausarías hoy?", "¿Qué campañas rinden bien pero se quedan sin presupuesto?"}
    assert len(bulk) == LIMIT and set(bulk[2:]) <= set(EVERYWHERE_ES)


def test_a_page_without_questions_of_its_own_draws_them_all_from_the_pool_in_its_language():
    home = for_page(navigation.HOME, "en", seed="conversation-1")

    assert len(set(home)) == LIMIT
    assert set(home) <= {question.text["en"] for question in STARTER_QUESTIONS if not question.pages}


def test_a_conversation_keeps_the_ideas_it_drew_and_another_one_draws_others():
    drawn = {tuple(for_page(navigation.HOME, "es", seed=f"conversation-{n}")) for n in range(20)}

    assert for_page(navigation.HOME, "es", seed="conversation-1") == for_page(navigation.HOME, "es",
                                                                              seed="conversation-1")
    assert len(drawn) > 1


def test_the_chat_is_named_capybaras_assistant_in_both_languages():
    assert panel._L["es"]["title"] == panel._L["en"]["title"] == "Capybaras Assistant"


def test_an_empty_chat_greets_and_shows_its_ideas_without_a_dropdown():
    app = AppTest.from_string(CHAT, default_timeout=30)
    app.run()

    html = " ".join(str(block.value) for block in app.markdown)
    assert "Hola, soy Capybaras Assistant." in html and "Ideas para preguntar" in html
    assert not app.expander
    assert app.button(key="aichat_t_panel_ideas_0").label == "¿Qué campañas pausarías hoy?"


def test_the_opening_screen_takes_the_height_the_thread_will_have():
    app = AppTest.from_string(CHAT, default_timeout=30)
    app.run()

    styles = " ".join(str(block.value) for block in app.markdown)
    assert f".st-key-aichat_t_panel_start {{height: {panel._STAGE_HEIGHT};" in styles
    assert f"height:{panel._STAGE_HEIGHT};" in panel._thread_box([], panel._L["es"])


def test_the_question_being_answered_waits_inside_the_thread_box_at_its_bottom():
    labels = panel._L["es"]
    history = [{"role": "user", "text": "¿primera?"}, {"role": "assistant", "text": "Primera respuesta"}]

    box = panel._thread_box(history, labels, panel._pending_turn("¿segunda?", ([], []), labels))

    assert box.count("flex-direction:column-reverse") == 1
    assert box.index("¿segunda?") < box.index("Primera respuesta") < box.index("¿primera?")


def test_clicking_an_idea_sends_it_as_the_question_and_the_ideas_go_away(monkeypatch):
    sent = []
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: sent.append(call) or iter(
        [{"type": "result", "text": "Pausaría C03.", "session_id": "s1"}]))
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string(CHAT, default_timeout=30)
    app.run()

    app.button(key="aichat_t_panel_ideas_0").click()
    app.run()
    # AppTest runs no fragment reruns: the answer's st.rerun(scope="fragment") becomes this full run.
    app.run()

    assert not app.exception
    assert sent[0]["input_text"] == "¿Qué campañas pausarías hoy?"
    assert [turn["text"] for turn in app.session_state["aichat_t_hist"]] == ["¿Qué campañas pausarías hoy?",
                                                                              "Pausaría C03."]
    assert not [button for button in app.button if str(button.key).startswith("aichat_t_panel_ideas")]

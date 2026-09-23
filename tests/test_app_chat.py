"""core/chat/app_chat - the one AI chat of the app and what the pages share with it.

ZERO network: the provider transport and every database read are patched.
AppTest.from_string / from_file only for what needs the Streamlit runtime.
"""
import types
import uuid

import pytest
from streamlit.testing.v1 import AppTest

import ai.client as ai_client
from ai import runtime
from core.chat import app_chat
from core.chat.screen_selection import FROM_AMAZON_ADS, FROM_HAND_UPLOAD, ScreenSelection


@pytest.fixture
def session(monkeypatch):
    state = {"selected_page": "🔍 Search Query Performance"}
    monkeypatch.setattr(app_chat, "st", types.SimpleNamespace(session_state=state))
    return state


@pytest.fixture
def recorded(monkeypatch):
    turns = []
    monkeypatch.setattr(app_chat.turns, "record", turns.append)
    return turns


def _analysis(module, key, subject="", profile_id="", country_code="", annotate=None):
    return app_chat.ChatAnalysis(module=module, key=key, subject=subject,
                                 documents=({"title": f"{module} doc", "content": key},),
                                 annotate=annotate, country_code=country_code, profile_id=profile_id)


class TestSharedState:
    def test_what_a_page_shares_stays_while_the_am_moves_to_another_page(self, session):
        app_chat.share_analysis(_analysis("sqp", "sqp:d1"))
        session["selected_page"] = "🏠 Inicio"

        assert [analysis.key for analysis in app_chat.shared_analyses(session["app_chat_modules"])] == ["sqp:d1"]
        assert session["app_chat_modules"]["sqp"].page == "🔍 Search Query Performance"

    def test_one_analysis_per_module_the_newest_replaces_the_previous(self, session):
        app_chat.share_analysis(_analysis("sqp", "sqp:d1"))
        app_chat.share_analysis(_analysis("sqp", "sqp:d2"))
        app_chat.share_analysis(_analysis("str", "str:1"))

        keys = [analysis.key for analysis in app_chat.shared_analyses(session["app_chat_modules"])]
        assert sorted(keys) == ["sqp:d2", "str:1"]

    def test_outdated_flags_only_the_analysis_it_names(self, session):
        app_chat.share_analysis(_analysis("sqp", "sqp:d1"))

        app_chat.mark_outdated("sqp", "sqp:d1")
        assert session["app_chat_modules"]["sqp"].state == "outdated"

        app_chat.mark_outdated("sqp", "sqp:other")
        assert "sqp" not in session["app_chat_modules"]

    def test_keep_current_is_true_only_for_the_shared_analysis(self, session):
        app_chat.share_analysis(_analysis("sqp", "sqp:d1"))
        app_chat.mark_outdated("sqp", "sqp:d1")

        assert app_chat.keep_current("sqp", "sqp:d2") is False
        assert app_chat.keep_current("sqp", "sqp:d1") is True
        assert session["app_chat_modules"]["sqp"].state == "current"

    def test_a_running_analysis_replaces_the_documents_with_its_state(self, session):
        app_chat.share_analysis(_analysis("sqp", "sqp:d1"))

        app_chat.report_running("sqp", "d2", finish=lambda analysis: _analysis("sqp", "sqp:d2"))

        assert app_chat.shared_analyses(session["app_chat_modules"]) == []
        assert session["app_chat_modules"]["sqp"].state == "running"


class TestRunningAnalysisFinishedElsewhere:
    @pytest.fixture
    def registry(self, session, monkeypatch):
        found = {}
        monkeypatch.setattr(app_chat.ai_runtime, "get", lambda module, digest: found.get((module, digest)))
        return found

    def test_an_analysis_that_finishes_while_the_am_is_on_another_page_reaches_the_chat(self, session, registry):
        app_chat.report_running("sqp", "d2", finish=lambda analysis: _analysis("sqp", f"sqp:{analysis.digest}"))
        session["selected_page"] = "🏠 Inicio"
        registry[("sqp", "d2")] = types.SimpleNamespace(digest="d2", running=False, done=True, failed=False)

        app_chat._finish_running_analyses()

        entry = session["app_chat_modules"]["sqp"]
        assert (entry.state, entry.analysis.key, entry.page) == ("current", "sqp:d2", "🔍 Search Query Performance")

    def test_one_that_failed_is_reported_as_failed(self, session, registry):
        app_chat.report_running("sqp", "d2", finish=lambda analysis: pytest.fail("a failed run has no documents"))
        registry[("sqp", "d2")] = types.SimpleNamespace(digest="d2", running=False, done=False, failed=True)

        app_chat._finish_running_analyses()

        assert session["app_chat_modules"]["sqp"].state == "failed"

    def test_one_still_running_stays_running(self, session, registry):
        app_chat.report_running("sqp", "d2", finish=lambda analysis: pytest.fail("not done yet"))
        registry[("sqp", "d2")] = types.SimpleNamespace(digest="d2", running=True, done=False, failed=False)

        app_chat._finish_running_analyses()

        assert session["app_chat_modules"]["sqp"].state == "running"


class TestSessionComposition:
    def test_the_key_ignores_the_order_and_changes_only_with_the_shared_analyses(self):
        sqp, stored = _analysis("sqp", "sqp:d1"), _analysis("str", "str:111:8:5")

        key = app_chat.session_key([sqp, stored])

        assert key == app_chat.session_key([stored, sqp])
        assert key != app_chat.session_key([_analysis("sqp", "sqp:d2"), stored])

    def test_documents_are_only_the_analyses_the_am_shared(self):
        """Other accounts are read through the MCP when the model asks: nothing about them is pasted."""
        documents = app_chat.session_documents([_analysis("sqp", "sqp:d1")])

        assert [doc["title"] for doc in documents] == ["sqp doc"]
        assert app_chat.session_documents([]) == []

    def test_the_turn_note_names_the_page_and_the_state_of_every_analysis(self, session):
        session["selected_page"] = "📊 Search Term Report"
        app_chat.share_analysis(_analysis("str", "str:1", subject="Luna · US"), state=app_chat.AnalysisState.MISSING)
        session["selected_page"] = "🧲 DataDive Analyzer"
        app_chat.report_running("datadive", "d9", finish=lambda analysis: None)
        session["selected_page"] = "🔍 Search Query Performance"
        app_chat.report_failed("sqp")

        note = app_chat.turn_note("🏠 Inicio", session["app_chat_modules"])

        assert note.startswith("[Nota de la app, no la cites: el AM tiene abierta la pantalla «Inicio».")
        assert ("Search Term Report (Luna · US): no hay un análisis de lo que se ve. "
                "En los documentos sólo hay análisis anteriores.") in note
        assert "DataDive Analyzer: el análisis de lo que se ve se está generando." in note
        assert "Search Query Performance: el análisis de lo que se ve falló." in note

    def test_a_stored_analysis_left_generating_on_another_page_is_not_claimed_to_be_still_running(self, session):
        session["selected_page"] = "📊 Search Term Report"
        app_chat.report_running("str")

        away = app_chat.turn_note("🏠 Inicio", session["app_chat_modules"])
        there = app_chat.turn_note("📊 Search Term Report", session["app_chat_modules"])

        assert "cuando el AM dejó esa pantalla, el análisis se estaba generando; puede haber terminado." in away
        assert "Search Term Report: el análisis de lo que se ve se está generando." in there

    def test_without_analyses_the_note_says_so(self):
        assert "No hay análisis abiertos en esta sesión." in app_chat.turn_note("🏠 Inicio", {})


class TestMount:
    @pytest.fixture
    def mounted(self, session, monkeypatch):
        calls = []
        monkeypatch.setattr(app_chat, "floating_chat", lambda **kwargs: calls.append(kwargs))
        monkeypatch.setattr(app_chat.ads_scope, "request_scope",
                            lambda country_hint=None: {"hint": country_hint})
        monkeypatch.setattr(app_chat.ai_config, "AI_ENABLED", True)
        return calls

    def test_the_chat_opens_over_every_shared_analysis_and_nothing_else(self, session, mounted):
        app_chat.share_analysis(_analysis("str", "str:111:8:5", profile_id="111", country_code="MX"))

        app_chat.mount_app_chat("🔍 Search Query Performance", "am.test")

        call = mounted[-1]
        turn = call["turn"]()
        assert (call["chat_id"], call["agent"]) == ("app", "orchestrator")
        assert call["session_key"]() == "str:111:8:5"
        assert [doc["title"] for doc in turn.documents] == ["str doc"]
        assert "«Search Query Performance»" in turn.note

    def test_the_mount_reads_nothing_until_the_am_asks(self, session, mounted, monkeypatch):
        """Mounted on every page: only the key is computed on a render, never the account."""
        app_chat.share_analysis(_analysis("str", "str:1", profile_id="111"))
        reads = []
        monkeypatch.setattr(app_chat.ads_scope, "request_scope",
                            lambda country_hint=None: reads.append("scope"))

        app_chat.mount_app_chat("🏠 Inicio", "am.test")
        key = mounted[-1]["session_key"]()

        assert (key, reads) == ("str:1", [])
        mounted[-1]["turn"]()
        assert reads == ["scope"]

    def test_amazon_ads_keeps_the_region_it_opened_with_while_the_session_lasts(self, session, mounted):
        session["selected_page"] = "📊 Search Term Report"
        app_chat.share_analysis(_analysis("str", "str:1", country_code="DE"))
        on_report = app_chat.chat_turn("📊 Search Term Report")
        on_home = app_chat.chat_turn("🏠 Inicio")
        key_before = app_chat.chat_session_key()
        session["selected_page"] = "🔍 Search Query Performance"
        app_chat.share_analysis(_analysis("sqp", "sqp:1"))
        on_sqp = app_chat.chat_turn("🔍 Search Query Performance")

        assert [turn.ads_scope for turn in (on_report, on_home, on_sqp)] == [{"hint": "DE"}] * 3
        assert key_before != app_chat.chat_session_key()

    def test_answers_are_annotated_by_every_shared_analysis(self, session, mounted):
        app_chat.share_analysis(_analysis("str", "str:1", annotate=lambda t: t.replace("N01", "N01 (toy box)")))
        app_chat.share_analysis(_analysis("sqp", "sqp:1", annotate=lambda t: t.replace("Q02", "Q02 (luna)")))

        assert app_chat.chat_turn("🏠 Inicio").annotate("N01 y Q02") == "N01 (toy box) y Q02 (luna)"

    def test_a_question_sent_after_an_analysis_finished_in_the_background_reads_it(self, session, mounted,
                                                                                  monkeypatch):
        app_chat.report_running("sqp", "d2", finish=lambda analysis: _analysis("sqp", f"sqp:{analysis.digest}"))
        app_chat.mount_app_chat("🏠 Inicio", "am.test")
        send = mounted[-1]["turn"]
        monkeypatch.setattr(app_chat.ai_runtime, "get", lambda module, digest: types.SimpleNamespace(
            digest=digest, running=False, done=True, failed=False))

        turn = send()

        assert turn.documents[0] == {"title": "sqp doc", "content": "sqp:d2"}
        assert "análisis disponible" in turn.note

    def test_with_ai_disabled_there_is_no_chat(self, session, mounted, monkeypatch):
        monkeypatch.setattr(app_chat.ai_config, "AI_ENABLED", False)

        app_chat.mount_app_chat("🏠 Inicio", "am.test")

        assert mounted == []

    def test_every_finished_turn_is_kept_with_the_page_and_the_user_it_was_mounted_for(self, session, mounted,
                                                                                         recorded):
        app_chat.mount_app_chat("📊 Search Term Report", "am.test")

        mounted[-1]["on_turn_finished"]("¿qué negativizo?", None, "No se pudo responder: timeout")

        assert [(turn.page, turn.username, turn.question) for turn in recorded] == [
            ("📊 Search Term Report", "am.test", "¿qué negativizo?")]


def _reply() -> runtime.ChatReply:
    return runtime.ChatReply(text="Frenar N01", blocks=None, tool_calls=("mcp__ppc_manager__breakdown",),
                             session_id="s1", model="claude-opus-5", cost_usd=0.21)


class TestRecordTurn:
    def test_an_answer_is_kept_as_the_am_read_it_with_the_account_of_the_page(self, session, recorded):
        session["selected_page"] = "📊 Search Term Report"
        app_chat.share_analysis(_analysis("str", "str:1", subject="Dermaglós · US", profile_id="279177258676903"))

        app_chat.record_turn("📊 Search Term Report", "am.test", "¿qué negativizo?", _reply(),
                             "Frenar N01 (toy box)")

        [turn] = recorded
        assert (turn.username, turn.page, turn.question) == ("am.test", "📊 Search Term Report", "¿qué negativizo?")
        assert (turn.answer, turn.error) == ("Frenar N01 (toy box)", None)
        assert (turn.ads_profile_id, turn.ads_account) == ("279177258676903", "Dermaglós · US")
        assert (turn.tools, turn.model, turn.cost_usd) == (("mcp__ppc_manager__breakdown",), "claude-opus-5", 0.21)

    def test_the_account_is_only_the_one_on_the_page_the_am_asked_from(self, session, recorded):
        """The chat reaches every account; the row says which one the AM had open, and no other."""
        session["selected_page"] = "📊 Search Term Report"
        app_chat.share_analysis(_analysis("str", "str:1", subject="Dermaglós · US", profile_id="279177258676903"))
        session["selected_page"] = "🔍 Search Query Performance"
        app_chat.share_analysis(_analysis("sqp", "sqp:1", subject="marca luna · semana 36"))

        app_chat.record_turn("🏠 Inicio", "am.test", "¿cómo va?", _reply(), "Bien")
        app_chat.record_turn("🔍 Search Query Performance", "am.test", "¿cómo va?", _reply(), "Bien")

        assert [(turn.ads_profile_id, turn.ads_account) for turn in recorded] == [(None, None), (None, None)]

    def test_a_page_without_an_analysis_keeps_the_account_it_has_selected(self, session, recorded):
        session["selected_page"] = "🧠 Bid Optimizer"
        app_chat.share_selection(ScreenSelection(module="Bid Optimizer", account="Luna Kids · US",
                                                 source=FROM_AMAZON_ADS, profile_id="111"))

        app_chat.record_turn("🧠 Bid Optimizer", "am.test", "¿qué bid?", _reply(), "B0CYLMJJJC a $1.37")
        app_chat.record_turn("🏠 Inicio", "am.test", "¿cómo va?", _reply(), "Bien")

        assert [(turn.ads_profile_id, turn.ads_account) for turn in recorded] == [("111", "Luna Kids · US"),
                                                                                   (None, None)]

    def test_the_analysis_of_the_page_wins_over_its_selection(self, session, recorded):
        session["selected_page"] = "📊 Search Term Report"
        app_chat.share_selection(ScreenSelection(module="Search Term Report", account="Luna Kids · US",
                                                 source=FROM_AMAZON_ADS, profile_id="111"))
        app_chat.share_analysis(_analysis("str", "str:1", subject="Dermaglós · US", profile_id="279177258676903"))

        app_chat.record_turn("📊 Search Term Report", "am.test", "¿qué negativizo?", _reply(), "Frenar N01")

        assert (recorded[0].ads_profile_id, recorded[0].ads_account) == ("279177258676903", "Dermaglós · US")

    def test_a_hand_upload_on_screen_has_no_account(self, session, recorded):
        session["selected_page"] = "🧠 Bid Optimizer"
        app_chat.share_selection(ScreenSelection(module="Bid Optimizer", account="str.csv", source=FROM_HAND_UPLOAD))

        app_chat.record_turn("🧠 Bid Optimizer", "am.test", "¿qué bid?", _reply(), "Sin cuenta")

        assert (recorded[0].ads_profile_id, recorded[0].ads_account) == (None, None)

    def test_a_page_whose_analysis_came_from_a_file_has_no_account(self, session, recorded):
        session["selected_page"] = "📊 Search Term Report"
        app_chat.share_analysis(_analysis("str", "str:file", subject="search_terms.csv"))

        app_chat.record_turn("📊 Search Term Report", "am.test", "¿qué negativizo?", _reply(), "Frenar N01")

        assert (recorded[0].ads_profile_id, recorded[0].ads_account) == (None, None)

    def test_a_failed_turn_keeps_the_question_and_the_error_the_am_read(self, session, recorded):
        app_chat.record_turn("🏠 Inicio", "am.test", "¿qué pasa?", None, "No se pudo responder: timeout")

        [turn] = recorded
        assert (turn.question, turn.answer, turn.error) == ("¿qué pasa?", None, "No se pudo responder: timeout")
        assert (turn.tools, turn.model, turn.cost_usd) == ((), None, None)

    def test_the_turns_of_a_session_share_a_conversation_and_another_session_starts_its_own(self, session,
                                                                                          recorded, monkeypatch):
        app_chat.record_turn("🏠 Inicio", "am.test", "uno", _reply(), "a")
        app_chat.record_turn("📊 Search Term Report", "am.test", "dos", _reply(), "b")
        monkeypatch.setattr(app_chat, "st", types.SimpleNamespace(session_state={}))
        app_chat.record_turn("🏠 Inicio", "am.test", "tres", _reply(), "c")

        first, second, other = (turn.conversation_id for turn in recorded)
        assert first == second != other
        assert str(uuid.UUID(first)) == first  # the column is a uuid


def test_the_orchestrator_is_an_agent_with_the_three_tool_profiles():
    assert runtime.agent_tools("orchestrator") == ["amazon_ads", "datadive", "ppc_manager"]
    assert runtime._agent("orchestrator")["meta"]["model"] == "claude-opus-5-5"
    assert runtime._agent("orchestrator")["meta"]["effort"] == "high"
    assert runtime._agent("orchestrator")["meta"]["timeout_s"] == "3600"
    system = runtime._agent("orchestrator")["system"]
    for section in ("<fuentes>", "<elegir_la_fuente>", "<estado_de_la_app>", "<clientes>"):
        assert section in system
    # El índice antes que el contenido: bajar todos los análisis "por las dudas" es justo lo que
    # el MCP viene a evitar.
    assert "list_analyses" in system and "no bajes todos por las dudas" in system
    # Sin la serie diaria, el trend sólo aparecía cuando el AM tipeaba los valores.
    assert "`daily_metrics`" in system and "La curva día a día" in system
    # La serie no reemplaza al análisis: la primera versión de esta regla mandaba a la serie una
    # pregunta por el CVR de un ASIN contra el tramo anterior, y el modelo negaba un dato que existía.
    assert "antes de decir que no existe" in system
    # Sin el desglose, un reparto por portfolio se contestaba "no lo tengo" o con 40 llamadas campaña por campaña.
    assert "`breakdown`, en una sola llamada" in system
    # Nada de otras cuentas viaja pegado: se cruzan por el MCP, en una llamada y no cuenta por cuenta.
    assert "Últimos análisis" not in system and "Cuenta:" not in system
    assert "`accounts_overview`" in system and "Nunca las consultes una por una" in system


def test_a_chat_turn_asks_the_provider_about_tools_only_when_the_am_sends(monkeypatch):
    health = []
    monkeypatch.setattr(ai_client, "available_tools", lambda: health.append(1) or frozenset({"datadive"}))
    sent = []
    monkeypatch.setattr(runtime.client, "ask", lambda **call: sent.append(call) or {"text": "ok", "session_id": "s1"})
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    monkeypatch.setattr(app_chat.ads_scope, "request_scope", lambda country_hint=None: None)

    app = AppTest.from_string("""
from core.chat import app_chat
app_chat.mount_app_chat("🏠 Inicio", "am.test")
""", default_timeout=30)
    app.run()
    assert not app.exception
    assert health == []

    text, session_id = runtime.ask_followup("orchestrator", None, "¿qué campañas tiene Luna?",
                                            note=app_chat.turn_note("🏠 Inicio", {}))


    assert (text, session_id, len(health)) == ("ok", "s1", 1)
    assert sent[0]["tools"] == ["datadive"]  # amazon_ads needs an account; datadive is served
    assert sent[0]["input_text"].endswith("\n\n¿qué campañas tiene Luna?")


def test_an_answer_keeps_the_annotation_of_the_analyses_it_was_answered_from(monkeypatch):
    """The page shown later can reuse the same row ids for another client: an answer is annotated once."""
    monkeypatch.setattr(runtime.client, "ask_stream",
                        lambda **call: iter([{"type": "result", "text": "Frenar N01", "session_id": "s1"}]))
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string("""
import streamlit as st
from core.chat.panel import ChatTurn, floating_chat
term = st.session_state.get("term_on_screen", "toy box")
floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k", turn=lambda: ChatTurn(
    annotate=lambda text: text.replace("N01", f"N01 ({term})")))
""", default_timeout=30)
    app.run()
    app.text_area(key="aichat_t_q_0").input("¿qué negativizo?")
    app.button[0].click()
    app.run()

    app.session_state["term_on_screen"] = "otro cliente"
    app.run()

    assert not app.exception
    html = " ".join(str(block.value) for block in app.markdown)
    assert "Frenar N01 (toy box)" in html and "otro cliente" not in html
    assert app.session_state["aichat_t_hist"][1]["text"] == "Frenar N01"
    assert app.text_area(key="aichat_t_q_2").value == ""


def test_the_turn_is_built_when_the_am_sends_and_never_on_a_plain_render(monkeypatch):
    sent = []
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: sent.append(call) or iter(
        [{"type": "result", "text": "ok", "session_id": "s1"}]))
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string("""
import streamlit as st
from core.chat.panel import ChatTurn, floating_chat
builds = st.session_state.setdefault("builds", [])

def turn():
    builds.append(1)
    return ChatTurn(documents=[{"title": "lectura", "content": str(len(builds))}])

floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k", turn=turn)
""", default_timeout=30)
    app.run()
    app.run()
    assert app.session_state["builds"] == []  # two renders, nothing built

    app.text_area(key="aichat_t_q_0").input("¿qué hay?")
    app.button[0].click()
    app.run()
    builds_at_send = len(app.session_state["builds"])
    app.run()  # AppTest reruns the whole script on a click, where a fragment-scoped rerun is refused

    assert not app.exception
    assert builds_at_send == 1
    assert sent[0]["context"][0]["content"] == "1"


_REPORTING_CHAT = """
import streamlit as st
from core.chat.panel import ChatTurn, floating_chat
finished = st.session_state.setdefault("finished", [])
floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k",
              turn=lambda: ChatTurn(annotate=lambda text: text.replace("N01", "N01 (toy box)")),
              on_turn_finished=lambda question, reply, shown: finished.append((question, reply, shown)))
"""


def _ask(app: AppTest, question: str) -> None:
    app.run()
    app.text_area(key="aichat_t_q_0").input(question)
    app.button[0].click()
    app.run()
    app.run()  # a plain render afterwards reports nothing new


def test_the_chat_reports_each_finished_turn_once_with_what_the_am_read(monkeypatch):
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: iter([
        {"type": "result", "text": "Frenar N01", "session_id": "s1", "tool_calls": ["mcp__ppc_manager__breakdown"],
         "total_cost_usd": 0.05}]))
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string(_REPORTING_CHAT, default_timeout=30)

    _ask(app, "¿qué negativizo?")

    assert not app.exception
    [(question, reply, shown)] = app.session_state["finished"]
    assert (question, shown) == ("¿qué negativizo?", "Frenar N01 (toy box)")
    assert (reply.tool_calls, reply.model, reply.cost_usd) == (
        ("mcp__ppc_manager__breakdown",), "claude-opus-5-5", 0.05)


def test_a_turn_the_provider_could_not_answer_is_reported_with_the_error_the_am_read(monkeypatch):
    def unreachable(**call):
        raise ai_client.ProviderDown("No se pudo contactar al AI provider.")

    monkeypatch.setattr(runtime.client, "ask_stream", unreachable)
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string(_REPORTING_CHAT, default_timeout=30)

    _ask(app, "¿qué pasa?")

    assert not app.exception
    assert app.session_state["finished"] == [
        ("¿qué pasa?", None, "No se pudo responder: No se pudo contactar al AI provider.")]


def test_the_app_boots_on_home_with_the_chat_mounted(monkeypatch):
    monkeypatch.setenv("AGENCY_OS_LOCAL_MODE", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setattr(app_chat.ads_scope, "request_scope", lambda country_hint=None: None)
    monkeypatch.setattr(ai_client, "available_tools", lambda: pytest.fail("the mount must not ask the provider"))
    monkeypatch.setattr(app_chat.ai_config, "AI_ENABLED", True)

    app = AppTest.from_file("app.py", default_timeout=120)
    app.run()

    assert not app.exception
    assert app.session_state["aichat_app_hist"] == []

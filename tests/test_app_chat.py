"""core/app_chat - the one AI chat of the app and what the pages share with it.

ZERO network: the provider transport and every database read are patched.
AppTest.from_string / from_file only for what needs the Streamlit runtime.
"""
import types
from datetime import date, datetime, timezone

import pytest
from streamlit.testing.v1 import AppTest

import ai.client as ai_client
from ai import runtime
from core import app_chat
from core.ai_analysis.account_summaries import AccountAnalysis
from core.ai_analysis.store import StoredAnalysis
from core.amazon_ads.report_provider import ProfileOption


@pytest.fixture
def session(monkeypatch):
    state = {"selected_page": "🔍 Search Query Performance"}
    monkeypatch.setattr(app_chat, "st", types.SimpleNamespace(session_state=state))
    return state


def _analysis(module, key, subject="", profile_id="", country_code="", annotate=None):
    return app_chat.ChatAnalysis(module=module, key=key, subject=subject,
                                 documents=({"title": f"{module} doc", "content": key},),
                                 annotate=annotate, country_code=country_code, profile_id=profile_id)


def _account(profile_id, analysis_id, cliente="Luna", country="US"):
    profile = ProfileOption(profile_id=profile_id, account_id=1, cliente=cliente, account_name=cliente,
                            country_code=country, currency_code="USD", account_type="seller", timezone="UTC",
                            status="active", data_from=None, data_through=date(2026, 9, 14), refreshed_on=None,
                            last_success_at=None, last_error="")
    stored = StoredAnalysis(
        id=analysis_id, module="str", subject_id=profile_id, window_start=date(2026, 8, 16),
        window_end=date(2026, 9, 14), lang="es", params={"brand_terms": []}, params_digest="", input_digest="",
        agent_version="", status="done", trigger="scheduled", requested_by="", job_id=None,
        source_last_success_at=None, result={"synthesis": {"situation": f"síntesis {cliente}"}}, model="",
        duration_ms=None, created_at=None, finished_at=datetime(2026, 9, 15, 13, 5, tzinfo=timezone.utc))
    return AccountAnalysis(profile, f"{cliente} · {country}", stored)


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

    def test_documents_are_the_shared_analyses_then_the_accounts_summaries(self):
        documents = app_chat.session_documents([_analysis("sqp", "sqp:d1")], [_account("222", 40)])

        assert [doc["title"] for doc in documents] == [
            "sqp doc", "Últimos análisis de Search Terms guardados por cuenta (1 de 1)"]
        assert app_chat.session_documents([], []) == []

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
        monkeypatch.setattr(app_chat.ads_account_picker, "request_scope",
                            lambda country_hint=None: {"hint": country_hint})
        monkeypatch.setattr(app_chat, "_stored_account_analyses", lambda: [_account("111", 8), _account("222", 9)])
        monkeypatch.setattr(app_chat.ai_config, "AI_ENABLED", True)
        return calls

    def test_the_chat_opens_over_every_shared_analysis_without_repeating_the_account_on_screen(
            self, session, mounted):
        app_chat.share_analysis(_analysis("str", "str:111:8:5", profile_id="111", country_code="MX"))

        app_chat.mount_app_chat("🔍 Search Query Performance")

        call = mounted[-1]
        turn = call["turn"]()
        assert (call["chat_id"], call["agent"]) == ("app", "orchestrator")
        assert call["session_key"]() == "str:111:8:5"
        assert turn.documents[0]["title"] == "str doc"
        assert "Cuenta: Luna · US" in turn.documents[1]["content"]
        assert turn.documents[1]["title"].endswith("(1 de 1)")
        assert "«Search Query Performance»" in turn.note

    def test_the_mount_reads_nothing_until_the_am_asks(self, session, mounted, monkeypatch):
        """Mounted on every page: only the key is computed on a render, never the documents or the account."""
        app_chat.share_analysis(_analysis("str", "str:1", profile_id="111"))
        reads = []
        monkeypatch.setattr(app_chat, "_stored_account_analyses", lambda: reads.append("db") or [])
        monkeypatch.setattr(app_chat.ads_account_picker, "request_scope",
                            lambda country_hint=None: reads.append("scope"))

        app_chat.mount_app_chat("🏠 Inicio")
        key = mounted[-1]["session_key"]()

        assert (key, reads) == ("str:1", [])
        mounted[-1]["turn"]()
        assert reads == ["db", "scope"]

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
        app_chat.mount_app_chat("🏠 Inicio")
        send = mounted[-1]["turn"]
        monkeypatch.setattr(app_chat.ai_runtime, "get", lambda module, digest: types.SimpleNamespace(
            digest=digest, running=False, done=True, failed=False))

        turn = send()

        assert turn.documents[0] == {"title": "sqp doc", "content": "sqp:d2"}
        assert "análisis disponible" in turn.note

    def test_a_database_that_did_not_answer_is_said_instead_of_passing_as_no_analyses(self, session, mounted,
                                                                                      monkeypatch):
        monkeypatch.setattr(app_chat, "_stored_account_analyses", lambda: None)

        turn = app_chat.chat_turn("🏠 Inicio")

        assert turn.documents == []
        assert "no se pudieron leer ahora" in turn.note

    def test_with_ai_disabled_there_is_no_chat(self, session, mounted, monkeypatch):
        monkeypatch.setattr(app_chat.ai_config, "AI_ENABLED", False)

        app_chat.mount_app_chat("🏠 Inicio")

        assert mounted == []


def test_a_database_that_fails_is_told_apart_from_one_with_no_analyses(monkeypatch):
    app_chat._stored_account_analyses.clear()
    monkeypatch.setattr(app_chat, "_rest_credentials", lambda: ("http://db", "key"))

    def _down(rest):
        raise ConnectionError("database down")
    monkeypatch.setattr(app_chat, "latest_account_analyses", _down)
    assert app_chat._stored_account_analyses() is None

    app_chat._stored_account_analyses.clear()
    monkeypatch.setattr(app_chat, "_rest_credentials", lambda: None)
    assert app_chat._stored_account_analyses() == []
    app_chat._stored_account_analyses.clear()


def test_the_orchestrator_is_an_agent_with_amazon_ads_and_datadive_tools():
    assert runtime.agent_tools("orchestrator") == ["amazon_ads", "datadive"]
    assert runtime._agent("orchestrator")["meta"]["model"] == "claude-opus-5"
    assert runtime._agent("orchestrator")["meta"]["effort"] == "high"
    assert runtime._agent("orchestrator")["meta"]["timeout_s"] == "3600"
    system = runtime._agent("orchestrator")["system"]
    for section in ("<fuentes>", "<elegir_la_fuente>", "<estado_de_la_app>", "<clientes>"):
        assert section in system


def test_a_chat_turn_asks_the_provider_about_tools_only_when_the_am_sends(monkeypatch):
    health = []
    monkeypatch.setattr(ai_client, "available_tools", lambda: health.append(1) or frozenset({"datadive"}))
    sent = []
    monkeypatch.setattr(runtime.client, "ask", lambda **call: sent.append(call) or {"text": "ok", "session_id": "s1"})
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    monkeypatch.setattr(app_chat.ads_account_picker, "request_scope", lambda country_hint=None: None)
    monkeypatch.setattr(app_chat, "_stored_account_analyses", lambda: [])

    app = AppTest.from_string("""
from core import app_chat
app_chat.mount_app_chat("🏠 Inicio")
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
from core.ai_chat import ChatTurn, floating_chat
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
from core.ai_chat import ChatTurn, floating_chat
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


def test_the_app_boots_on_home_with_the_chat_mounted(monkeypatch):
    monkeypatch.setenv("AGENCY_OS_LOCAL_MODE", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setattr(app_chat, "_stored_account_analyses", lambda: [])
    monkeypatch.setattr(app_chat.ads_account_picker, "request_scope", lambda country_hint=None: None)
    monkeypatch.setattr(ai_client, "available_tools", lambda: pytest.fail("the mount must not ask the provider"))
    monkeypatch.setattr(app_chat.ai_config, "AI_ENABLED", True)

    app = AppTest.from_file("app.py", default_timeout=120)
    app.run()

    assert not app.exception
    assert app.session_state["aichat_app_hist"] == []

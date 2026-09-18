"""What the chat reads about stored analyses, and when a turn sends it."""
from datetime import date, datetime, timezone

from ai import runtime
from core.ai_analysis.chat_context import analysis_chat_documents, current_analysis_text, in_memory_analysis
from core.ai_analysis.store import StoredAnalysis


def _analysis(analysis_id, situation, **overrides):
    values = dict(
        id=analysis_id, module="str", subject_id="111", window_start=date(2026, 8, 16), window_end=date(2026, 9, 14),
        lang="es", params={"target_acos": 30, "price": 30.0, "harvest_target_acos": 30, "harvest_price": None,
                           "harvest_min_clicks": 15, "brand_terms": ["luna"]},
        params_digest="p", input_digest=f"d{analysis_id}", agent_version="v", status="done", trigger="scheduled",
        requested_by="scheduler", job_id=None, source_last_success_at=None,
        result={"negativos": [{"row_id": "N01", "razon": "no convierte", "categoria": "generico",
                               "advertencia": "revisar portfolio"}],
                "harvest": [], "campanas": [{"campaign": "LK - Broad", "diagnostico": "sangra"}],
                "synthesis": {"situation": situation, "week_actions": ["Negativizar N01"], "mid_term": [],
                              "risks": [{"type": "GASTO", "detail": "alto", "urgency": "ALTA"}]}},
        model="opus", duration_ms=90000, created_at=None,
        finished_at=datetime(2026, 9, 15, 13, 5, tzinfo=timezone.utc),
        negative_records=[{"Search Term": "cheap toy box", "Campaign": "LK - Broad", "Clicks": 40, "Orders": 0,
                           "Spend": 25.0, "Regla": "R2"}],
        harvest_records=[],
    )
    values.update(overrides)
    return StoredAnalysis(**values)


def test_the_current_analysis_carries_every_opinion_with_its_term_and_the_earlier_ones_their_synthesis():
    docs = analysis_chat_documents(_analysis(8, "Hoy sangra"), [_analysis(5, "Ayer estaba bien")],
                                   currency_code="USD")

    current, earlier = docs
    assert "Período: 16/08/2026 a 14/09/2026 · generado 15/09/2026 10:05" in current["content"]
    assert "precio harvest sin cargar" in current["content"] and "brand terms: luna" in current["content"]
    assert ("N01 · cheap toy box · LK - Broad · R2 · 40 clicks · 0 órdenes · gasto $25.00 → generico: no convierte"
            " · advertencia: revisar portfolio") in current["content"]
    assert "- LK - Broad: sangra" in current["content"]
    assert "Situación: Ayer estaba bien" in earlier["content"] and "N01 ·" not in earlier["content"]


def test_without_any_stored_analysis_the_chat_has_no_documents():
    assert analysis_chat_documents(None, [], currency_code="USD") == []
    assert [doc["title"][:31] for doc in analysis_chat_documents(None, [_analysis(5, "s")], currency_code="USD")] \
        == ["Análisis IA anteriores de esta "]


def test_another_analysis_on_screen_starts_a_new_chat_session_and_keeps_the_thread():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string("""
import streamlit as st
from core.chat.panel import ChatTurn, floating_chat
floating_chat(chat_id="str", agent="str", session_key=lambda: st.session_state.get("shown", "8"),
              turn=lambda: ChatTurn(documents=[{"title": "t", "content": "c"}]))
""", default_timeout=30)
    app.run()
    app.session_state["aichat_str_sid"] = "session-over-analysis-8"
    app.session_state["aichat_str_hist"] = [{"role": "user", "text": "hola"}]
    app.run()
    assert app.session_state["aichat_str_sid"] == "session-over-analysis-8"

    app.session_state["shown"] = "9"
    app.run()

    assert not app.exception
    assert app.session_state["aichat_str_sid"] is None
    assert app.session_state["aichat_str_hist"] == [{"role": "user", "text": "hola"}]


def test_a_turn_sends_the_documents_only_when_it_opens_a_session(monkeypatch):
    sent = []
    monkeypatch.setattr(runtime.client, "ask", lambda **call: sent.append(call["context"]) or
                        {"text": "ok", "session_id": "s-new"})
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    docs = [{"title": "Análisis", "content": "c"}]

    runtime.ask_followup("str", None, "¿qué priorizo?", context_docs=docs)
    runtime.ask_followup("str", "s-new", "¿y después?", context_docs=docs)

    assert sent == [docs, []]


def _recording_provider(monkeypatch):
    sent = []
    monkeypatch.setattr(runtime.client, "ask", lambda **call: sent.append(call) or
                        {"text": "ok", "session_id": "s-new"})
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    return sent


def test_the_app_note_goes_ahead_of_every_question(monkeypatch):
    sent = _recording_provider(monkeypatch)

    runtime.ask_followup("orchestrator", None, "¿qué priorizo?", note="[pantalla SQP]")
    runtime.ask_followup("orchestrator", "s-new", "¿y en STR?", note="[pantalla STR]")

    assert [call["input_text"] for call in sent] == ["[pantalla SQP]\n\n¿qué priorizo?",
                                                     "[pantalla STR]\n\n¿y en STR?"]


def test_a_new_session_carries_the_visible_thread_without_the_failed_turns(monkeypatch):
    sent = _recording_provider(monkeypatch)
    thread = [{"role": "user", "text": "¿qué negativizo?"},
              {"role": "assistant", "text": "No se pudo responder: timeout", "error": True},
              {"role": "user", "text": "¿qué negativizo?"},
              {"role": "assistant", "text": "N01 y N04."}]
    docs = [{"title": "Análisis", "content": "c"}]

    runtime.ask_followup("orchestrator", None, "¿y el harvest?", context_docs=docs, thread=thread)
    runtime.ask_followup("orchestrator", "s-new", "¿y después?", context_docs=docs, thread=thread)

    opening, resumed = (call["context"] for call in sent)
    assert opening[:1] == docs and resumed == []
    assert opening[1] == {"title": runtime.CONVERSATION_TITLE,
                          "content": "AM: ¿qué negativizo?\n\nAM: ¿qué negativizo?\n\nAsistente: N01 y N04."}


def test_the_carried_thread_keeps_only_the_latest_turns():
    thread = [{"role": "user", "text": f"pregunta {index}"} for index in range(20)]

    content = runtime.conversation_document(thread)["content"]

    assert content.startswith("AM: pregunta 8\n\n") and content.endswith("AM: pregunta 19")
    assert runtime.conversation_document([]) is None


def test_the_carried_thread_drops_whole_old_turns_and_keeps_the_last_question():
    long_answer = "x" * 11_950
    thread = [{"role": "user", "text": "listame las campañas"}, {"role": "assistant", "text": long_answer},
              {"role": "user", "text": "¿cuáles tienen presupuesto bajo?"}, {"role": "assistant", "text": "tres"}]

    content = runtime.conversation_document(thread)["content"]

    assert content.split("\n\n") == ["AM: ¿cuáles tienen presupuesto bajo?", "Asistente: tres"]


def test_the_carried_thread_has_the_answers_as_the_am_saw_them():
    thread = [{"role": "user", "text": "¿qué negativizo?"},
              {"role": "assistant", "text": "N01 y N04.", "shown": "N01 (toy box) y N04 (luna)."}]

    content = runtime.conversation_document(thread)["content"]

    assert content.endswith("Asistente: N01 (toy box) y N04 (luna).")


def test_an_uploaded_file_analysis_reads_like_a_stored_one():
    stored = _analysis(8, "Hoy sangra")
    in_memory = in_memory_analysis(
        stored.result, params=stored.params, lang="es", finished_at=stored.finished_at.timestamp(),
        negative_records=stored.negative_records, harvest_records=stored.harvest_records)

    stored_text = current_analysis_text(stored, "USD")
    file_text = current_analysis_text(in_memory, "USD")

    assert file_text.replace("Período: el del archivo subido", "Período: 16/08/2026 a 14/09/2026") == stored_text

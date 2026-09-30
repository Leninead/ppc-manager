"""The chat answers on a thread of its own: a page change while it answers loses neither the question nor the reply."""
import threading
import time

from streamlit.testing.v1 import AppTest

from ai import runtime
from core.chat import panel

CHAT = """
from core.chat.panel import ChatTurn, floating_chat
floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k", turn=lambda: ChatTurn(),
              starters=lambda: ["¿Qué campañas pausarías hoy?"])
"""


def _quiet_runtime(monkeypatch, ask_stream):
    monkeypatch.setattr(runtime.client, "ask_stream", ask_stream)
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])


def _wait_done(pending: dict) -> None:
    deadline = time.monotonic() + 5
    while not pending["done"] and time.monotonic() < deadline:
        time.sleep(0.01)


def test_the_answer_keeps_arriving_after_the_run_that_asked_is_gone(monkeypatch):
    release = threading.Event()

    def slow_stream(**call):
        yield {"type": "tool", "name": "amazon_ads_campaigns"}
        release.wait(5)
        yield {"type": "result", "text": "Pausaría C03.", "session_id": "s1"}

    _quiet_runtime(monkeypatch, slow_stream)
    finished = []
    pending = panel._start_answer("orchestrator", "¿Qué pauso?", panel.ChatTurn(), [], "low", None,
                                  panel._L["es"], "k", lambda *turn: finished.append(turn))
    time.sleep(0.05)
    assert not pending["done"] and pending["asked"] == ["amazon_ads_campaigns"]

    release.set()
    _wait_done(pending)
    assert pending["answer"]["shown"] == "Pausaría C03." and pending["reply"].session_id == "s1"
    assert not finished  # the turn is recorded when a run collects it, not from the thread


def test_an_answer_that_landed_while_the_am_was_elsewhere_reaches_the_thread(monkeypatch):
    _quiet_runtime(monkeypatch, lambda **call: iter([{"type": "result", "text": "Pausaría C03.", "session_id": "s1"}]))
    pending = panel._start_answer("orchestrator", "¿Qué pauso?", panel.ChatTurn(), [], "low", None,
                                  panel._L["es"], "k", None)
    _wait_done(pending)
    app = AppTest.from_string(CHAT, default_timeout=30)
    app.session_state["aichat_t_pending"] = pending
    app.run()

    assert not app.exception
    assert [turn["text"] for turn in app.session_state["aichat_t_hist"]] == ["¿Qué pauso?", "Pausaría C03."]
    assert "aichat_t_pending" not in app.session_state
    assert not [button for button in app.button if str(button.key).startswith("aichat_t_panel_ideas")]


def test_a_failure_on_the_thread_becomes_the_answer_instead_of_hanging_the_chat(monkeypatch):
    def broken_stream(**call):
        raise RuntimeError("boom")

    _quiet_runtime(monkeypatch, broken_stream)
    pending = panel._start_answer("orchestrator", "¿Qué pauso?", panel.ChatTurn(), [], "low", None,
                                  panel._L["es"], "k", None)
    _wait_done(pending)
    assert pending["done"] and pending["answer"]["error"] and "boom" in pending["answer"]["shown"]

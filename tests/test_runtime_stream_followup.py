"""runtime.stream_followup: the same turn as ask_followup, with the component catalog, read as it arrives."""
from ai import runtime
from core import chat_components


def _quiet(monkeypatch, tools=None):
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: list(tools or []))
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])


def test_the_turn_is_ask_followups_plus_the_catalog_the_model_reads_and_the_schema_it_is_held_to(monkeypatch):
    _quiet(monkeypatch)
    asked, streamed = [], []
    monkeypatch.setattr(runtime.client, "ask", lambda **call: asked.append(call) or {"text": "", "session_id": "s"})
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: streamed.append(call) or iter(
        [{"type": "result", "text": "", "session_id": "s"}]))
    args = ("orchestrator", None, "¿qué campañas?")
    kwargs = dict(context_docs=[{"title": "a", "content": "b"}], note="[nota]",
                  thread=[{"role": "user", "text": "hola"}])

    runtime.ask_followup(*args, **kwargs)
    list(runtime.stream_followup(*args, **kwargs))

    assert streamed[0].pop("output_schema") == chat_components.SCHEMA and asked[0].pop("output_schema") is None
    assert streamed[0].pop("system") == asked[0].pop("system") + "\n\n" + chat_components.GUIDE
    # Without tools the answer still needs turns for the StructuredOutput call.
    assert streamed[0].pop("max_turns") == runtime._MAX_TOOL_TURNS
    assert asked[0].pop("max_turns") == 1
    assert streamed[0] == asked[0]
    assert "<componentes>" not in asked[0]["input_text"]


def test_a_turn_with_tools_keeps_the_tool_budget(monkeypatch):
    _quiet(monkeypatch, tools=["datadive"])
    streamed = []
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: streamed.append(call) or iter(
        [{"type": "result", "text": "", "session_id": "s"}]))
    list(runtime.stream_followup("orchestrator", None, "¿qué niches?"))
    assert streamed[0]["max_turns"] == runtime._MAX_TOOL_TURNS == 20


def test_tools_arrive_while_the_model_works_and_the_reply_carries_the_components(monkeypatch):
    _quiet(monkeypatch, tools=["datadive"])
    structured = {"blocks": [{"kind": "text", "text": "Hay 2"}, {"kind": "bars", "metric": "Keywords", "items": [
        {"label": "knife", "value": 382, "display": "382", "tone": "good"}]}]}
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: iter([
        {"type": "tool", "name": "mcp__datadive__list_niches"},
        {"type": "result", "text": "prosa previa", "structured_output": structured, "session_id": "s9",
         "tool_calls": ["mcp__datadive__list_niches"]}]))

    events = list(runtime.stream_followup("orchestrator", None, "¿qué niches?"))

    assert events[0] == {"type": "tool", "name": "mcp__datadive__list_niches"}
    reply = events[1]["reply"]
    assert reply.blocks == chat_components.normalize(structured)
    assert reply.text == "Hay 2\n\nKeywords\nknife: 382"
    assert reply.tool_calls == ("mcp__datadive__list_niches",)
    assert reply.session_id == "s9" and runtime._TOOLED_TURNS["s9"] is True


def test_an_answer_that_did_not_come_in_components_falls_back_to_its_text(monkeypatch):
    _quiet(monkeypatch)
    for structured in (None, {"blocks": [{"kind": "table", "columns": ["A"], "rows": []}]}):
        monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: iter([
            {"type": "result", "text": "Solo prosa", "structured_output": structured, "session_id": "s1"}]))
        reply = list(runtime.stream_followup("orchestrator", None, "¿?"))[-1]["reply"]
        assert reply.blocks is None and reply.text == "Solo prosa" and reply.tool_calls == ()

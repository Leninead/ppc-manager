"""What the Slack bot takes from ppc-manager without changing it: these fail the day the app moves under it."""
import inspect

from ai import client, runtime
from core.chat import ads_scope, components, panel
from services.slack_bot import batch_reply, charts, to_slack, turn

# The kinds to_slack converts itself; a new component lands in neither set and fails here first.
SLACK_NATIVE_KINDS = {"text", "kpis", "table", "alert", "action"}


def test_every_component_of_the_catalog_has_a_slack_rendering():
    assert {component.kind for component in components.CATALOG} == SLACK_NATIVE_KINDS | charts.KINDS


def test_the_private_call_builder_still_takes_a_guide_and_a_schema():
    parameters = inspect.signature(runtime._followup_call).parameters
    assert list(parameters)[:7] == ["slug", "session_id", "question", "ads_scope", "context_docs", "note", "thread"]
    assert {"guide", "output_schema", "effort"} <= set(parameters)
    assert list(inspect.signature(runtime._remember_session).parameters) == ["call", "resp"]


def test_the_panels_tool_labels_are_still_there():
    labels = panel._L["es"]
    assert panel._tool_labels(["mcp__ppc_manager__daily_metrics"], labels) == ["Serie diaria · Agency OS"]
    assert panel._failed_labels(["mcp__ppc_manager__daily_metrics"], ["mcp__ppc_manager__daily_metrics"],
                                labels) == ["Serie diaria · Agency OS"]


def test_the_ads_scope_helpers_stay_pure():
    assert {"build_vehicles", "pick_vehicle", "SLUG", "AccountVehicle"} <= set(dir(ads_scope))


def test_a_batch_turn_is_the_app_chats_call_with_the_batch_schema(monkeypatch):
    seen = {}

    def ask_stream(**call):
        seen.update(call)
        yield {"type": "tool", "name": "mcp__ppc_manager__daily_metrics"}
        yield {"type": "tool_result", "name": "mcp__ppc_manager__daily_metrics", "ok": False}
        yield {"type": "result", "session_id": "S9", "tool_calls": ["mcp__ppc_manager__daily_metrics"],
               "failed_tools": ["mcp__ppc_manager__daily_metrics"], "total_cost_usd": 0.1,
               "structured_output": {"answers": [{"questions": ["q1"], "blocks": [{"kind": "text", "text": "ok"}]}],
                                     "skipped": []}}

    monkeypatch.setattr(client, "available_tools", lambda: frozenset({"ppc_manager", "amazon_ads", "datadive"}))
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    monkeypatch.setattr(client, "ask_stream", ask_stream)
    heard = []
    outcome = turn.run(prompt="q1 · Lenin: ¿ok?", question_ids=["q1"], session_id=None, ads_scope=None,
                       documents=[{"title": "Directorio", "content": "x"}], note="[Nota]", effort=None,
                       on_tool=lambda name, ok: heard.append((name, ok)))

    assert seen["output_schema"] == batch_reply.SCHEMA
    assert seen["system"].endswith(batch_reply.GUIDE)
    assert seen["input_text"] == "[Nota]\n\nq1 · Lenin: ¿ok?"
    assert seen["context"] == [{"title": "Directorio", "content": "x"}]
    assert "amazon_ads" not in seen["tools"]
    assert heard == [("mcp__ppc_manager__daily_metrics", None), ("mcp__ppc_manager__daily_metrics", False)]
    assert outcome.session_id == "S9"
    assert [answer.question_ids for answer in outcome.reply.answers] == [("q1",)]
    assert outcome.cost_usd == 0.1


def test_the_rendering_offers_one_converter_per_native_kind():
    for component in components.CATALOG:
        if component.kind in charts.KINDS:
            continue
        converted, _ = to_slack._blocks(components.normalize({"blocks": [component.example]})[0])
        assert converted, component.kind

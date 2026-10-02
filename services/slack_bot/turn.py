"""One batch turn on the provider: the app chat's own call (agent, chat rules, skills, tools), batch schema included.

`runtime._followup_call` is private; tests/test_slack_bot_contract.py fails the day its signature changes.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai import client, runtime
from core.chat.app_chat import AGENT
from services.slack_bot import batch_reply

ToolListener = Callable[[str, bool | None], None]


@dataclass(frozen=True)
class TurnOutcome:
    reply: batch_reply.BatchReply
    session_id: str | None
    tool_calls: tuple[str, ...]
    failed_tools: tuple[str, ...]
    model: str | None
    cost_usd: float | None


def run(*, prompt: str, question_ids: list[str], session_id: str | None, ads_scope: dict | None,
        documents: list[dict], note: str, effort: str | None, on_tool: ToolListener) -> TurnOutcome:
    """Raises what `ai.client.ask_stream` raises; `on_tool(name, ok)` hears each tool, ok=None when it starts."""
    call = runtime._followup_call(AGENT, session_id, prompt, ads_scope, documents, note, None,
                                  guide=batch_reply.GUIDE, output_schema=batch_reply.SCHEMA, effort=effort)
    result = None
    for event in client.ask_stream(**call):
        kind = event.get("type")
        if kind == "tool":
            on_tool(str(event.get("name") or ""), None)
        elif kind == "tool_result":
            on_tool(str(event.get("name") or ""), event.get("ok") is not False)
        elif kind == "result":
            result = event
    if result is None:
        raise client.UpstreamError("El AI provider no devolvió la respuesta.")
    reply = batch_reply.read_reply(result.get("structured_output"), question_ids, str(result.get("text") or ""))
    return TurnOutcome(reply=reply, session_id=runtime._remember_session(call, result),
                       tool_calls=tuple(result.get("tool_calls") or ()),
                       failed_tools=tuple(result.get("failed_tools") or ()),
                       model=call["model"], cost_usd=result.get("total_cost_usd"))

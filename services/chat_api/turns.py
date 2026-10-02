"""One Slack batch answered with the app chat's own turn: agent, chat rules, skills, tools and the turn record.

Everything that needs the database or the provider happens here, so the bot that asks holds neither credential.
`runtime._followup_call` is private; tests/test_chat_api.py fails the day its signature changes.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ai import client as ai_client
from ai import runtime
from core.chat import account_directory, components, turns
from core.chat import panel as chat_panel
from core.chat.app_chat import AGENT
from services.chat_api import batch_reply
from services.chat_api.account_scope import REGION_COUNTRIES, AccountScopes, TurnScope

log = logging.getLogger(__name__)

Emit = Callable[[dict], None]

_LABELS = chat_panel._L["es"]
_MAX_TEXT = 200_000
_MAX_QUESTIONS = 50


@dataclass(frozen=True)
class Place:
    """Where the batch was asked: the model reads it in the turn's note."""

    direct: bool
    channel_name: str = ""
    client: str = ""
    country: str = ""


@dataclass(frozen=True)
class TurnRequest:
    conversation: str
    prompt: str
    question_ids: list[str]
    questions: list[tuple[str, str]]
    place: Place
    requested_by: str
    session_id: str | None = None
    session_region: str | None = None
    history: dict | None = None
    effort: str | None = None

    @classmethod
    def from_json(cls, body: object) -> TurnRequest:
        """Raises ValueError on anything malformed: the door answers 400 and the provider is never called."""
        if not isinstance(body, dict):
            raise ValueError("body must be an object")
        prompt = _text(body, "prompt", required=True)
        ids = body.get("question_ids")
        if not isinstance(ids, list) or not ids or len(ids) > _MAX_QUESTIONS or not all(
                isinstance(i, str) and i for i in ids):
            raise ValueError("question_ids must be a non-empty list of strings")
        raw_questions = body.get("questions")
        if not isinstance(raw_questions, list) or len(raw_questions) > _MAX_QUESTIONS:
            raise ValueError("questions must be a list")
        questions = []
        for item in raw_questions:
            if not isinstance(item, dict):
                raise ValueError("each question must be an object")
            questions.append((_text(item, "asker"), _text(item, "text")))
        place = body.get("place")
        if not isinstance(place, dict):
            raise ValueError("place must be an object")
        history = body.get("history")
        if history is not None and not (isinstance(history, dict) and isinstance(history.get("title"), str)
                                        and isinstance(history.get("content"), str)
                                        and len(history["content"]) <= _MAX_TEXT):
            raise ValueError("history must be a {title, content} document")
        effort = body.get("effort")
        return cls(conversation=_text(body, "conversation", required=True), prompt=prompt,
                   question_ids=list(ids), questions=questions,
                   place=Place(direct=bool(place.get("direct")), channel_name=_text(place, "channel_name"),
                               client=_text(place, "client"), country=_text(place, "country").upper()),
                   requested_by=_text(body, "requested_by"),
                   session_id=_text(body, "session_id") or None,
                   session_region=_text(body, "session_region") or None,
                   history=history, effort=effort if isinstance(effort, str) and effort else None)


def answer_turn(request: TurnRequest, emit: Emit, *, scopes: AccountScopes,
                directory: Callable[[], dict | None] = account_directory.directory_document,
                record: Callable[[turns.ChatTurnRecord], None] = turns.record) -> None:
    """Emits one {"type": "tool"|"tool_result"} event per tool, then a "result" or an "error" event, and returns."""
    scope = scopes.for_country(request.place.country, request.requested_by)
    session = request.session_id
    if session and request.session_region != scope.region:
        # Opened for another Amazon Ads region; the bot asks again with the thread as history.
        emit({"type": "error", "kind": "session_lost", "message": "la sesión es de otra región de Amazon Ads"})
        return
    documents = [] if session else [document for document in (directory(), request.history) if document]
    call = runtime._followup_call(AGENT, session, request.prompt, scope.ads_scope, documents,
                                  turn_note(request.place, scope), None, guide=batch_reply.GUIDE,
                                  output_schema=batch_reply.SCHEMA, effort=request.effort)
    try:
        result = _stream(call, emit)
    except ai_client.QuotaExceeded as exc:
        _record(record, request, error=str(exc))
        emit({"type": "error", "kind": "quota", "message": str(exc), "retry_after": exc.retry_after})
        return
    except ai_client.UpstreamError as exc:
        if session:
            # A session the provider no longer has: the bot asks again with the thread as history.
            emit({"type": "error", "kind": "session_lost", "message": str(exc)})
            return
        _record(record, request, error=str(exc))
        emit({"type": "error", "kind": "failed", "message": str(exc)})
        return
    except ai_client.AIError as exc:
        _record(record, request, error=str(exc))
        emit({"type": "error", "kind": "unavailable", "message": str(exc)})
        return

    reply = batch_reply.read_reply(result.get("structured_output"), request.question_ids,
                                   str(result.get("text") or ""))
    tool_calls = tuple(result.get("tool_calls") or ())
    failed_tools = tuple(result.get("failed_tools") or ())
    _record(record, request, reply=reply, tool_calls=tool_calls, model=call["model"],
            cost_usd=result.get("total_cost_usd"))
    emit({"type": "result",
          "answers": [{"question_ids": list(answer.question_ids), "blocks": answer.blocks} for answer in reply.answers],
          "skipped": reply.skipped, "missing": list(reply.missing),
          "session_id": runtime._remember_session(call, result), "region": scope.region, "new_session": not session,
          "sources": chat_panel._tool_labels(tool_calls, _LABELS),
          "failed_sources": chat_panel._failed_labels(tool_calls, failed_tools, _LABELS),
          "tool_count": len(tool_calls), "model": call["model"], "cost_usd": result.get("total_cost_usd")})


def turn_note(place: Place, scope: TurnScope) -> str:
    """App state the model reads ahead of the batch; nobody in Slack sees it."""
    where = ("por mensaje directo" if place.direct else
             f"en el canal #{place.channel_name or 'sin nombre'}, en un hilo donde pueden escribir varias personas "
             "del equipo")
    lines = [f"estás respondiendo en Slack, {where}.",
             "No hay pantallas ni análisis abiertos: los análisis guardados de cada cuenta se leen con las "
             "herramientas de ppc-manager."]
    if place.client:
        country = f" ({place.country})" if place.country else ""
        lines.append(f"Este canal es del cliente {place.client}{country}: si una pregunta no nombra la cuenta, es de "
                     "ese cliente.")
    if scope.region:
        lines.append(f"Amazon Ads en vivo lee la región {scope.region} ({REGION_COUNTRIES.get(scope.region, '')}); "
                     "las cuentas de otras regiones, con las herramientas de ppc-manager.")
    else:
        lines.append("Amazon Ads en vivo no está disponible en este turno: usá las herramientas de ppc-manager.")
    return "[Nota de la app, no la cites: " + " ".join(lines) + "]"


def _stream(call: dict, emit: Emit) -> dict:
    result = None
    for event in ai_client.ask_stream(**call):
        kind = event.get("type")
        name = str(event.get("name") or "")
        if kind == "tool":
            labels = chat_panel._tool_labels([name], _LABELS)
            emit({"type": "tool", "name": name, "label": labels[0] if labels else None})
        elif kind == "tool_result":
            emit({"type": "tool_result", "name": name, "ok": event.get("ok") is not False})
        elif kind == "result":
            result = event
    if result is None:
        raise ai_client.UpstreamError("El AI provider no devolvió la respuesta.")
    return result


def _record(record: Callable[[turns.ChatTurnRecord], None], request: TurnRequest, *,
            reply: batch_reply.BatchReply | None = None, error: str | None = None,
            tool_calls: tuple[str, ...] = (), model: str | None = None, cost_usd: float | None = None) -> None:
    """Best effort, like the app's: one chat_turns row per turn, the whole batch in it."""
    answer = "\n\n".join(components.plain_text(answer.blocks) for answer in reply.answers) if reply else None
    try:
        record(turns.ChatTurnRecord(
            conversation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, request.conversation)),
            username=request.requested_by or "slack", page="slack",
            question="\n".join(f"{asker}: {text}" for asker, text in request.questions) or request.prompt,
            answer=answer if reply is not None else None, error=None if reply is not None else (error or "error"),
            tools=tool_calls, model=model, cost_usd=cost_usd, ads_account=request.place.client or None))
    except Exception:  # noqa: BLE001 — a missing row never costs the answer
        log.exception("chat turn not recorded for %s", request.conversation)


def _text(body: dict, key: str, required: bool = False) -> str:
    value = body.get(key)
    if value is None or value == "":
        if required:
            raise ValueError(f"{key} is required")
        return ""
    if not isinstance(value, str) or len(value) > _MAX_TEXT:
        raise ValueError(f"{key} must be a string of at most {_MAX_TEXT} characters")
    return value

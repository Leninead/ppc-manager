"""The bot's only way to the chat: a POST to PPC Manager's internal chat API, read as a stream of JSON lines.

The bot holds no database key and no provider secret; this token only lets it ask the chat a batch.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import requests

TURN_PATH = "/v1/slack/turns"
_CONNECT_TIMEOUT_S = 10


class ChatError(Exception):
    """The chat could not answer this batch; the message is what the thread reads."""


class ChatQuota(ChatError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class SessionLost(ChatError):
    """The thread's session cannot be resumed (the provider lost it, or its region moved): ask again with history."""


@dataclass(frozen=True)
class BatchAnswer:
    question_ids: tuple[str, ...]
    blocks: list[dict]


@dataclass(frozen=True)
class BatchReply:
    answers: tuple[BatchAnswer, ...] = ()
    skipped: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatOutcome:
    reply: BatchReply
    session_id: str | None
    region: str | None
    new_session: bool
    sources: tuple[str, ...] = ()
    failed_sources: tuple[str, ...] = ()
    tool_count: int = 0
    cost_usd: float | None = None


class ChatClient:
    def __init__(self, url: str, token: str, timeout_s: int = 3600, post=requests.post):
        self._url = url.rstrip("/") + TURN_PATH
        self._token = token
        self._timeout_s = timeout_s
        self._post = post

    def turn(self, payload: dict, on_source: Callable[[str], None]) -> ChatOutcome:
        """Raises ChatError (ChatQuota, SessionLost) when there is no answer; `on_source` hears each source read."""
        try:
            response = self._post(self._url, json=payload, headers={"Authorization": f"Bearer {self._token}"},
                                  stream=True, timeout=(_CONNECT_TIMEOUT_S, self._timeout_s))
        except requests.RequestException as exc:
            raise ChatError("no pude llegar al chat de PPC Manager") from exc
        with response:
            if response.status_code == 401:
                raise ChatError("el chat de PPC Manager no reconoce al bot (revisar CHAT_API_TOKEN)")
            if response.status_code != 200:
                raise ChatError(f"el chat de PPC Manager respondió {response.status_code}")
            try:
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line.decode("utf-8"))
                    kind = event.get("type")
                    if kind == "tool" and event.get("label"):
                        on_source(str(event["label"]))
                    elif kind == "result":
                        return _outcome(event)
                    elif kind == "error":
                        raise _error(event)
            except (requests.RequestException, ValueError) as exc:
                raise ChatError("el chat de PPC Manager cortó la respuesta") from exc
        raise ChatError("el chat de PPC Manager cortó la respuesta")


def _outcome(event: dict) -> ChatOutcome:
    answers = tuple(BatchAnswer(tuple(str(i) for i in answer.get("question_ids") or ()),
                                list(answer.get("blocks") or ()))
                    for answer in event.get("answers") or () if isinstance(answer, dict))
    skipped = {str(k): str(v) for k, v in (event.get("skipped") or {}).items()}
    return ChatOutcome(reply=BatchReply(answers, skipped, tuple(str(i) for i in event.get("missing") or ())),
                       session_id=event.get("session_id") or None, region=event.get("region") or None,
                       new_session=bool(event.get("new_session")),
                       sources=tuple(str(s) for s in event.get("sources") or ()),
                       failed_sources=tuple(str(s) for s in event.get("failed_sources") or ()),
                       tool_count=int(event.get("tool_count") or 0), cost_usd=event.get("cost_usd"))


def _error(event: dict) -> ChatError:
    message = str(event.get("message") or "error desconocido")
    kind = event.get("kind")
    if kind == "quota":
        return ChatQuota(message, int(event.get("retry_after") or 60))
    if kind == "session_lost":
        return SessionLost(message)
    return ChatError(message)

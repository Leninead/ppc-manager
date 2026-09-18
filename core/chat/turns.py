"""The app chat's turns, one row each in `chat_turns`: written by the app, never read back by it.

Migration 016 grants the app INSERT alone, which is why the write asks for no row in return.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import requests

from core.integrations.store import _Rest, _rest_credentials

log = logging.getLogger(__name__)

TABLE = "chat_turns"


@dataclass(frozen=True)
class ChatTurnRecord:
    """One finished turn. `answer` is None when it failed, and `error` holds what the AM read then."""

    conversation_id: str
    username: str
    page: str
    question: str
    answer: str | None
    error: str | None
    tools: tuple[str, ...] = ()
    model: str | None = None
    cost_usd: float | None = None
    ads_profile_id: str | None = None
    ads_account: str | None = None


def record(turn: ChatTurnRecord) -> None:
    """Best effort: a turn the database refuses is logged, and the chat goes on."""
    credentials = _rest_credentials()
    if credentials is None:
        return
    try:
        _Rest(*credentials).insert(TABLE, asdict(turn))
    except requests.RequestException as exc:
        log.warning("chat turn not recorded (conversation %s, page %s): %s",
                    turn.conversation_id, turn.page, _describe(exc))


def _describe(exc: requests.RequestException) -> str:
    response = exc.response
    if response is None:
        return str(exc)
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return f"HTTP {response.status_code}"
    # Not `details`: on a constraint violation Postgres echoes the whole row, question and answer included.
    return f"HTTP {response.status_code} {body.get('code', '')} {body.get('message', '')}".rstrip()

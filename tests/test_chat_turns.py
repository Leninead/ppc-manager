"""core/chat/turns: every finished chat turn becomes one row the app writes and never reads back.

ZERO network: PostgREST is a fake session behind the real transport.
"""
import dataclasses
import json
import logging
import pathlib
import re

import pytest
import requests

from core.chat import turns as chat_turns
from core.integrations.store import _Rest

MIGRATION = pathlib.Path("deploy/db/migrations/016_chat_turns.sql")


class _FakeSession:
    def __init__(self, response: requests.Response | None = None, error: Exception | None = None):
        self.posts: list[dict] = []
        self._response = response
        self._error = error

    def post(self, url, json=None, headers=None, timeout=None, params=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        if self._error is not None:
            raise self._error
        return self._response


def _response(status: int, body: dict | str = "") -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = (json.dumps(body) if isinstance(body, dict) else body).encode()
    return response


@pytest.fixture
def database(monkeypatch):
    def connect(response: requests.Response | None = None, error: Exception | None = None) -> _FakeSession:
        # Not `response or ...`: a 4xx/5xx Response is falsy.
        session = _FakeSession(response if response is not None else _response(201), error)
        monkeypatch.setattr(chat_turns, "_rest_credentials", lambda: ("http://rest-gateway", "jwt"))
        monkeypatch.setattr(chat_turns, "_Rest", lambda url, key: _Rest(url, key, session=session))
        return session
    return connect


def _turn(**changes) -> chat_turns.ChatTurnRecord:
    turn = chat_turns.ChatTurnRecord(
        conversation_id="7d0f3c2e-1b4a-4c55-9a51-0f2a1c9b7e10", username="am.test", page="📊 Search Term Report",
        question="¿qué negativizo en Dermaglós?", answer="Frenar N01 (toy box)", error=None,
        tools=("mcp__ppc_manager__breakdown", "mcp__ppc_manager__breakdown"), model="claude-opus-5",
        cost_usd=0.1234, ads_profile_id="279177258676903", ads_account="Dermaglós · US")
    return dataclasses.replace(turn, **changes)


def test_a_turn_is_one_row_written_without_asking_it_back(database):
    session = database()

    chat_turns.record(_turn())

    [post] = session.posts
    assert post["url"] == "http://rest-gateway/rest/v1/chat_turns"
    # Asking for the row back needs SELECT, which the app does not have: PostgREST would answer 403.
    assert post["headers"]["Prefer"] == "return=minimal"
    assert json.loads(json.dumps(post["json"])) == {
        "conversation_id": "7d0f3c2e-1b4a-4c55-9a51-0f2a1c9b7e10", "username": "am.test",
        "page": "📊 Search Term Report", "question": "¿qué negativizo en Dermaglós?",
        "answer": "Frenar N01 (toy box)", "error": None,
        "tools": ["mcp__ppc_manager__breakdown", "mcp__ppc_manager__breakdown"], "model": "claude-opus-5",
        "cost_usd": 0.1234, "ads_profile_id": "279177258676903", "ads_account": "Dermaglós · US"}


def test_a_failed_turn_travels_with_its_error_and_no_answer(database):
    session = database()

    chat_turns.record(_turn(answer=None, error="No se pudo responder: timeout", tools=(), model=None,
                            cost_usd=None))

    row = session.posts[0]["json"]
    assert (row["answer"], row["error"], row["tools"], row["model"], row["cost_usd"]) == (
        None, "No se pudo responder: timeout", (), None, None)


@pytest.mark.parametrize("failure", [
    {"response": _response(404, {"code": "PGRST205", "message": "Could not find the table 'public.chat_turns'"})},
    {"response": _response(403, {"code": "42501", "message": "permission denied for table chat_turns"})},
    {"response": _response(502, "Bad Gateway")},
    {"error": requests.ConnectionError("rest-gateway unreachable")},
    {"error": requests.Timeout("read timed out")},
], ids=["table-missing", "grant-missing", "gateway-error", "down", "timeout"])
def test_a_database_that_refuses_the_turn_is_logged_and_the_chat_goes_on(database, caplog, failure):
    database(**failure)

    with caplog.at_level(logging.WARNING, logger="core.chat.turns"):
        chat_turns.record(_turn())

    [warning] = caplog.records
    assert "chat turn not recorded" in warning.getMessage()
    assert "7d0f3c2e-1b4a-4c55-9a51-0f2a1c9b7e10" in warning.getMessage()


def test_the_log_never_carries_what_the_am_asked_or_read(database, caplog):
    """A constraint violation echoes the whole failing row in `details`."""
    database(response=_response(400, {
        "code": "23514", "message": 'new row for relation "chat_turns" violates check constraint',
        "details": "Failing row contains (1, ¿qué negativizo en Dermaglós?, Frenar N01 (toy box))"}))

    with caplog.at_level(logging.WARNING, logger="core.chat.turns"):
        chat_turns.record(_turn())

    message = caplog.records[0].getMessage()
    assert "HTTP 400 23514" in message
    assert "negativizo" not in message and "Frenar" not in message


def test_without_a_database_nothing_is_sent(monkeypatch):
    monkeypatch.setattr(chat_turns, "_rest_credentials", lambda: None)
    monkeypatch.setattr(chat_turns, "_Rest", lambda url, key: pytest.fail("there is no database to write to"))

    chat_turns.record(_turn())


def _grants_to_web_user(sql: str) -> list[str]:
    return [" ".join(grant.split()) for grant in re.findall(r"grant\s+(.+?)\s+to\s+web_user\s*;", sql, re.S | re.I)]


def test_the_migration_lets_the_app_insert_every_field_it_sends_and_nothing_else():
    sql = MIGRATION.read_text(encoding="utf-8")

    # schema.sql hands web_user CRUD on every new table and sequence: 016 has to take it back first.
    assert "revoke all on chat_turns from web_user;" in sql
    assert "revoke all on sequence chat_turns_id_seq from web_user;" in sql
    insert_grant, sequence_grant = _grants_to_web_user(sql)
    granted = re.fullmatch(r"insert \((.+)\) on chat_turns", insert_grant).group(1)
    # A field the app sends without an INSERT grant on its column makes every turn fail with 403.
    assert {column.strip() for column in granted.split(",")} == {
        field.name for field in dataclasses.fields(chat_turns.ChatTurnRecord)}
    assert sequence_grant == "usage on sequence chat_turns_id_seq"


def test_every_field_the_app_sends_is_a_column_of_the_table():
    sql = MIGRATION.read_text(encoding="utf-8")
    table = re.search(r"create table if not exists chat_turns \((.+?)\n\);", sql, re.S).group(1)
    columns = {line.split()[0] for line in table.splitlines() if line.strip() and not line.strip().startswith("constraint")}

    assert {field.name for field in dataclasses.fields(chat_turns.ChatTurnRecord)} <= columns
    assert {"id", "created_at"} <= columns

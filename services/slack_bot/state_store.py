"""What survives a restart: each thread's progress, answers not yet posted, who asked when, the last event heard."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from services.slack_bot.conversations import Conversation, Key

_SCHEMA = """
create table if not exists conversations (
    channel text not null,
    thread_ts text not null,
    direct integer not null default 0,
    session_id text,
    session_started_at real not null default 0,
    region text,
    watermark text not null default '0',
    carried text not null default '{}',
    excluded text not null default '[]',
    owes_answers integer not null default 0,
    updated_at real not null,
    primary key (channel, thread_ts)
);
create table if not exists deliveries (
    channel text not null,
    thread_ts text not null,
    payload text not null,
    done integer not null default 0,
    attempts integer not null default 0,
    primary key (channel, thread_ts)
);
create table if not exists questions_asked (user text not null, at real not null);
create index if not exists questions_asked_by_user on questions_asked (user, at);
create table if not exists meta (key text primary key, value text not null);
"""

LAST_EVENT_TS = "last_event_ts"
DAY_S = 24 * 3600
# A day past the provider's 7-day session retention: older threads have nothing left to resume.
STATE_RETENTION_S = 8 * DAY_S


class StateStore:
    def __init__(self, path: Path, clock=time.time):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("pragma journal_mode=wal")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._clock = clock

    def save(self, conversation: Conversation, delivery: dict | None = None) -> None:
        """With `delivery`, the turn's answers are stored in the same transaction as the watermark that passed them,
        so a crash can neither lose them nor ask the model again."""
        with self._lock:
            self._db.execute("begin")
            try:
                self._db.execute(
                    "insert into conversations (channel, thread_ts, direct, session_id, session_started_at, region, "
                    "watermark, carried, excluded, owes_answers, updated_at) values (?,?,?,?,?,?,?,?,?,?,?) "
                    "on conflict (channel, thread_ts) do update set direct=excluded.direct, "
                    "session_id=excluded.session_id, session_started_at=excluded.session_started_at, "
                    "region=excluded.region, watermark=excluded.watermark, carried=excluded.carried, "
                    "excluded=excluded.excluded, owes_answers=excluded.owes_answers, updated_at=excluded.updated_at",
                    (conversation.channel, conversation.thread_ts, int(conversation.direct), conversation.session_id,
                     conversation.session_started_at, conversation.region, conversation.watermark,
                     json.dumps(conversation.carried), json.dumps(sorted(conversation.excluded)),
                     int(conversation.owes_answers), conversation.updated_at or self._clock()))
                if delivery is not None:
                    self._db.execute("insert or replace into deliveries (channel, thread_ts, payload, done, attempts) "
                                     "values (?, ?, ?, 0, 0)",
                                     (conversation.channel, conversation.thread_ts,
                                      json.dumps(delivery, ensure_ascii=False)))
                self._db.execute("commit")
            except BaseException:
                self._db.execute("rollback")
                raise

    def find(self, channel: str, thread_ts: str) -> Conversation | None:
        with self._lock:
            row = self._db.execute(f"select {_COLUMNS} from conversations where channel=? and thread_ts=?",
                                   (channel, thread_ts)).fetchone()
        return _conversation(row) if row else None

    def recent(self, since: float) -> list[Conversation]:
        with self._lock:
            rows = self._db.execute(f"select {_COLUMNS} from conversations where updated_at >= ? "
                                    "order by updated_at", (since,)).fetchall()
        return [_conversation(row) for row in rows]

    def pending_delivery(self, key: Key) -> tuple[dict, int, int] | None:
        """(payload, steps already done, failed attempts) of answers a turn produced and Slack has not fully shown."""
        with self._lock:
            row = self._db.execute("select payload, done, attempts from deliveries where channel=? and thread_ts=?",
                                   key).fetchone()
        return (json.loads(row[0]), int(row[1]), int(row[2])) if row else None

    def pending_delivery_keys(self) -> list[Key]:
        with self._lock:
            return [(channel, thread_ts) for channel, thread_ts
                    in self._db.execute("select channel, thread_ts from deliveries").fetchall()]

    def delivery_step_done(self, key: Key, done: int) -> None:
        with self._lock:
            self._db.execute("update deliveries set done=? where channel=? and thread_ts=?", (done, *key))

    def delivery_failed(self, key: Key) -> int:
        with self._lock:
            self._db.execute("update deliveries set attempts=attempts+1 where channel=? and thread_ts=?", key)
            row = self._db.execute("select attempts from deliveries where channel=? and thread_ts=?", key).fetchone()
        return int(row[0]) if row else 0

    def drop_delivery(self, key: Key) -> None:
        with self._lock:
            self._db.execute("delete from deliveries where channel=? and thread_ts=?", key)

    def record_question(self, user: str) -> None:
        with self._lock:
            self._db.execute("insert into questions_asked (user, at) values (?, ?)", (user, self._clock()))

    def questions_last_day(self, user: str) -> int:
        with self._lock:
            row = self._db.execute("select count(*) from questions_asked where user=? and at > ?",
                                   (user, self._clock() - DAY_S)).fetchone()
        return int(row[0])

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("select value from meta where key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute("insert into meta (key, value) values (?, ?) "
                             "on conflict (key) do update set value=excluded.value", (key, value))

    def prune(self, conversations_older_than_s: float = STATE_RETENTION_S) -> None:
        now = self._clock()
        with self._lock:
            self._db.execute("delete from conversations where updated_at < ?", (now - conversations_older_than_s,))
            self._db.execute("delete from questions_asked where at < ?", (now - 2 * DAY_S,))


_COLUMNS = ("channel, thread_ts, direct, session_id, session_started_at, region, watermark, carried, excluded, "
            "owes_answers, updated_at")


def _conversation(row: tuple) -> Conversation:
    (channel, thread_ts, direct, session_id, session_started_at, region, watermark, carried, excluded,
     owes_answers, updated_at) = row
    return Conversation(channel=channel, thread_ts=thread_ts, direct=bool(direct), session_id=session_id,
                        session_started_at=session_started_at, region=region, watermark=watermark,
                        carried={str(k): int(v) for k, v in json.loads(carried or "{}").items()},
                        excluded=set(json.loads(excluded or "[]")), owes_answers=bool(owes_answers),
                        updated_at=updated_at)

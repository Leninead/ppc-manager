"""Each Slack thread the bot answers in: its provider session, how far it has read and whether it owes answers."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum

from services.slack_bot.batch import ts_value

Key = tuple[str, str]  # (channel, thread_ts)

# The provider deletes sessions after 7 days; resuming one that old fails, so start over a day before.
SESSION_MAX_AGE_S = 6 * 24 * 3600


class Stage(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    ANSWERING = "answering"


@dataclass
class Conversation:
    channel: str
    thread_ts: str
    direct: bool = False
    session_id: str | None = None
    session_started_at: float = 0.0
    region: str | None = None
    watermark: str = "0"
    # Questions a turn left unanswered: read once more past the watermark, then reported.
    carried: dict[str, int] = field(default_factory=dict)
    # Mentions refused at the door (daily limit): shown as conversation, never answered.
    excluded: set[str] = field(default_factory=set)
    stage: Stage = Stage.IDLE
    owes_answers: bool = False
    failures: int = 0
    updated_at: float = 0.0

    @property
    def key(self) -> Key:
        return (self.channel, self.thread_ts)

    def session_to_resume(self, now: float) -> str | None:
        """The session while the provider still keeps it; the chat API drops it too if its region changed."""
        if not self.session_id or now - self.session_started_at > SESSION_MAX_AGE_S:
            return None
        return self.session_id


class ConversationRegistry:
    """The only place that changes a conversation's stage; every method is safe across threads."""

    def __init__(self, clock=time.time):
        self._conversations: dict[Key, Conversation] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def restore(self, conversation: Conversation) -> None:
        with self._lock:
            self._conversations[conversation.key] = conversation

    def snapshot(self, key: Key) -> Conversation | None:
        with self._lock:
            found = self._conversations.get(key)
            return replace(found, carried=dict(found.carried), excluded=set(found.excluded)) if found else None

    def keys_owing_answers(self) -> list[Key]:
        with self._lock:
            return [key for key, conversation in self._conversations.items()
                    if conversation.owes_answers or conversation.carried]

    def mention(self, channel: str, thread_ts: str, direct: bool) -> bool:
        """A new question arrived; True when the conversation has to be queued now."""
        with self._lock:
            conversation = self._conversations.setdefault(
                (channel, thread_ts), Conversation(channel, thread_ts))
            conversation.direct = direct
            conversation.owes_answers = True
            conversation.updated_at = self._clock()
            if conversation.stage != Stage.IDLE:
                return False
            conversation.stage = Stage.QUEUED
            return True

    def exclude(self, key: Key, ts: str, direct: bool) -> None:
        with self._lock:
            conversation = self._conversations.setdefault(key, Conversation(*key))
            conversation.direct = direct
            conversation.excluded.add(ts)

    def start(self, key: Key) -> Conversation | None:
        """The turn begins: questions that arrive from now on wait for the next one."""
        with self._lock:
            conversation = self._conversations.get(key)
            if conversation is None:
                return None
            conversation.stage = Stage.ANSWERING
            conversation.owes_answers = False
            return replace(conversation, carried=dict(conversation.carried), excluded=set(conversation.excluded))

    def finish(self, key: Key, *, watermark: str | None = None, session_id: str | None = None,
               region: str | None = None, new_session: bool = False, carried: dict[str, int] | None = None,
               failed: bool = False, still_owed: bool = False) -> bool:
        """Stores what the turn read and answered; True when the conversation must be queued again.

        `still_owed` is a batch that left questions for the next one: they are past the new watermark.
        """
        with self._lock:
            conversation = self._conversations[key]
            now = self._clock()
            if still_owed:
                conversation.owes_answers = True
            if watermark is not None:
                conversation.watermark = watermark
                conversation.excluded = {ts for ts in conversation.excluded if _after(ts, watermark)}
            if session_id:
                if new_session or session_id != conversation.session_id:
                    conversation.session_started_at = now
                conversation.session_id = session_id
                conversation.region = region
            if carried is not None:
                conversation.carried = carried
            conversation.failures = conversation.failures + 1 if failed else 0
            conversation.updated_at = now
            again = failed or conversation.owes_answers or bool(conversation.carried)
            conversation.stage = Stage.QUEUED if again else Stage.IDLE
            return again

    def close(self, key: Key, watermark: str) -> None:
        """Nothing up to `watermark` will be answered here, and the thread waits idle for a new mention."""
        with self._lock:
            conversation = self._conversations[key]
            conversation.watermark = watermark
            conversation.carried = {}
            conversation.excluded = {ts for ts in conversation.excluded if _after(ts, watermark)}
            conversation.owes_answers = False
            conversation.failures = 0
            conversation.updated_at = self._clock()
            conversation.stage = Stage.IDLE

    def forget_idle(self, older_than_s: float) -> int:
        """Drops idle threads nobody wrote in for that long; the store keeps them as long as it keeps anything."""
        cutoff = self._clock() - older_than_s
        with self._lock:
            stale = [key for key, conversation in self._conversations.items()
                     if conversation.stage == Stage.IDLE and not conversation.carried
                     and conversation.updated_at < cutoff]
            for key in stale:
                del self._conversations[key]
        return len(stale)

    def give_up(self, key: Key, watermark: str) -> bool:
        """Too many failures: what was asked so far is dropped; True when newer questions still wait."""
        with self._lock:
            conversation = self._conversations[key]
            conversation.watermark = watermark
            conversation.carried = {}
            conversation.excluded = {ts for ts in conversation.excluded if _after(ts, watermark)}
            conversation.failures = 0
            conversation.updated_at = self._clock()
            conversation.stage = Stage.QUEUED if conversation.owes_answers else Stage.IDLE
            return conversation.owes_answers


def _after(ts: str, watermark: str) -> bool:
    return ts_value(ts) > ts_value(watermark)

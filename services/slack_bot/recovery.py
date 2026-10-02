"""After a restart: threads that still owed answers, and mentions Slack sent while the bot was away.

Socket Mode makes no promise to redeliver events from a disconnection, so allowed channels are read back from
the last event heard. Unknown threads start reading there, so nothing answered before is answered again.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from slack_sdk.errors import SlackApiError

from services.slack_bot import slack_text
from services.slack_bot.slack_text import is_direct_channel
from services.slack_bot.access import AccessPolicy
from services.slack_bot.answering import BotIdentity, ThreadAnswerer
from services.slack_bot.batch import ts_value
from services.slack_bot.conversations import Conversation, ConversationRegistry, Stage
from services.slack_bot.poster import SlackPoster
from services.slack_bot.scheduler import TurnScheduler
from services.slack_bot.settings import BotSettings
from services.slack_bot.state_store import LAST_EVENT_TS, STATE_RETENTION_S, StateStore

log = logging.getLogger(__name__)

_HISTORY_PAGES = 3


class Recovery:
    def __init__(self, *, slack, poster: SlackPoster, answerer: ThreadAnswerer, registry: ConversationRegistry,
                 scheduler: TurnScheduler, store: StateStore, settings: BotSettings, identity: BotIdentity,
                 access: AccessPolicy, clock=time.time):
        self._slack = slack
        self._access = access
        self._poster = poster
        self._answerer = answerer
        self._registry = registry
        self._scheduler = scheduler
        self._store = store
        self._settings = settings
        self._identity = identity
        self._clock = clock

    def run(self) -> int:
        """Queues what is owed; returns how many threads were queued."""
        self._store.prune()
        queued = set()
        for conversation in self._store.recent(self._clock() - STATE_RETENTION_S):
            conversation.stage = Stage.IDLE
            self._registry.restore(conversation)
            if conversation.owes_answers or conversation.carried:
                queued.add(self._queue(conversation.channel, conversation.thread_ts, conversation.direct))
        # Answers a turn produced before the restart and Slack has not fully shown: posted before anything new.
        for channel, thread_ts in self._store.pending_delivery_keys():
            known = self._registry.snapshot((channel, thread_ts))
            if known is None:
                self._registry.restore(Conversation(channel, thread_ts, direct=is_direct_channel(channel)))
            direct = known.direct if known else is_direct_channel(channel)
            queued.add(self._queue(channel, thread_ts, direct))
        for channel, thread_ts in self._missed_mentions():
            if self._registry.snapshot((channel, thread_ts)) is None:
                self._registry.restore(Conversation(channel, thread_ts, watermark=self._floor()))
            queued.add(self._queue(channel, thread_ts, False))
        if queued:
            log.info("recovery queued %d thread(s)", len(queued))
        return len(queued)

    def _queue(self, channel: str, thread_ts: str, direct: bool) -> tuple[str, str]:
        if self._registry.mention(channel, thread_ts, direct):
            self._scheduler.submit((channel, thread_ts))
        snapshot = self._registry.snapshot((channel, thread_ts))
        if snapshot is not None:
            self._store.save(snapshot)
        return channel, thread_ts

    def _floor(self) -> str:
        last = self._store.get_meta(LAST_EVENT_TS)
        floor = max(ts_value(last or "0"), Decimal(str(self._clock() - self._settings.recovery_hours * 3600)))
        return str(floor)

    def _missed_mentions(self) -> list[tuple[str, str]]:
        if not self._store.get_meta(LAST_EVENT_TS):
            return []
        floor = self._floor()
        found: list[tuple[str, str]] = []
        for channel in self._channels_to_read():
            try:
                for message in self._history(channel, floor):
                    ts = str(message.get("ts") or "")
                    if not message.get("bot_id") and slack_text.mentions(str(message.get("text") or ""),
                                                                         self._identity.user_id):
                        found.append((channel, str(message.get("thread_ts") or ts)))
                    elif ts_value(str(message.get("latest_reply") or "0")) > ts_value(floor):
                        replies = self._answerer.read_thread(channel, ts, floor)
                        if any(not reply.from_bot and ts_value(reply.ts) > ts_value(floor)
                               and slack_text.mentions(reply.text, self._identity.user_id) for reply in replies):
                            found.append((channel, ts))
            except SlackApiError as exc:
                log.warning("channel %s not read back: %s", channel, exc.response.get("error"))
        return list(dict.fromkeys(found))

    def _channels_to_read(self) -> list[str]:
        if self._settings.every_channel:
            return sorted(str(channel.get("id")) for channel in self._access.member_channels() if channel.get("id"))
        return sorted(self._settings.allowed_channels)

    def _history(self, channel: str, oldest: str) -> list[dict]:
        messages: list[dict] = []
        cursor = None
        for _ in range(_HISTORY_PAGES):
            extra = {"cursor": cursor} if cursor else {}
            response = self._poster.call(self._slack.conversations_history, channel=channel, oldest=oldest,
                                         limit=200, **extra)
            messages.extend(response.get("messages") or [])
            cursor = (response.get("response_metadata") or {}).get("next_cursor")
            if not (response.get("has_more") and cursor):
                break
        return messages

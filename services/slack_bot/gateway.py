"""Slack's events in: who asked what and where, checked at the door and handed to the thread's queue.

Nothing slow happens here: Bolt acknowledges each event first, and the turn runs on the scheduler's workers.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict

from slack_sdk.errors import SlackApiError

from core.chat import starter_questions
from services.slack_bot import batch as batching
from services.slack_bot import slack_text, texts, to_slack
from services.slack_bot.slack_text import is_direct_channel
from services.slack_bot.access import AccessPolicy, Verdict
from services.slack_bot.answering import EYES, REFUSED, BotIdentity
from services.slack_bot.conversations import ConversationRegistry, Key
from services.slack_bot.poster import SlackPoster
from services.slack_bot.scheduler import TurnScheduler
from services.slack_bot.settings import BotSettings
from services.slack_bot.state_store import LAST_EVENT_TS, StateStore

log = logging.getLogger(__name__)

IDEAS_TITLE = "Ideas para preguntar"
_SEEN_EVENTS = 2000
_LAST_EVENT_EVERY_S = 30
# A DM's own messages; the rest (edits, deletions, joins) are not questions.
_DIRECT_SUBTYPES = frozenset({None, "file_share", "thread_broadcast"})


class Gateway:
    def __init__(self, *, poster: SlackPoster, access: AccessPolicy, registry: ConversationRegistry,
                 scheduler: TurnScheduler, store: StateStore, settings: BotSettings, identity: BotIdentity,
                 clock=time.time):
        self._poster = poster
        self._access = access
        self._registry = registry
        self._scheduler = scheduler
        self._store = store
        self._settings = settings
        self._identity = identity
        self._clock = clock
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._lock = threading.Lock()
        self._last_event_saved = 0.0

    def register(self, app) -> None:
        app.event("app_mention")(self.on_mention)
        app.event("message")(self.on_message)
        app.event("assistant_thread_started")(self.on_assistant_thread_started)
        app.event("assistant_thread_context_changed")(self.ignore)
        app.action(re.compile(rf"^{to_slack.IDEA_ACTION_PREFIX}\d+$"))(self.on_idea)

    def ignore(self) -> None:
        return None

    def on_mention(self, event: dict) -> None:
        """A mention in a channel, or in a DM, where Slack may send it as well as the message event."""
        self._heard(event)
        channel = str(event.get("channel") or "")
        self._take(channel=channel, user=str(event.get("user") or ""),
                   ts=str(event.get("ts") or ""), thread_ts=str(event.get("thread_ts") or event.get("ts") or ""),
                   text=str(event.get("text") or ""), has_files=bool(event.get("files")),
                   direct=event.get("channel_type") == "im" or is_direct_channel(channel))

    def on_message(self, event: dict) -> None:
        """Direct messages only: in a channel the bot answers when mentioned, and that comes as app_mention."""
        if event.get("channel_type") != "im" or event.get("bot_id") or event.get("subtype") not in _DIRECT_SUBTYPES:
            return
        self._heard(event)
        self._take(channel=str(event.get("channel") or ""), user=str(event.get("user") or ""),
                   ts=str(event.get("ts") or ""), thread_ts=str(event.get("thread_ts") or event.get("ts") or ""),
                   text=str(event.get("text") or ""), has_files=bool(event.get("files")), direct=True)

    def on_idea(self, ack, body: dict) -> None:
        """A click on an idea becomes a question in the clicker's name, posted where everyone sees it."""
        ack()
        user = str((body.get("user") or {}).get("id") or "")
        container = body.get("container") or {}
        channel = str((body.get("channel") or {}).get("id") or container.get("channel_id") or "")
        message = body.get("message") or {}
        thread_ts = str(message.get("thread_ts") or container.get("thread_ts") or message.get("ts") or "")
        question = str(((body.get("actions") or [{}])[0]).get("value") or "").strip()
        direct = is_direct_channel(channel)
        if not (user and channel and thread_ts and question):
            return
        verdict = self._access.check(channel, user, direct)
        if verdict != Verdict.ALLOWED:
            self._refuse(channel, user, thread_ts, verdict)
            return
        if self._over_limit(user):
            self._limit_notice(channel, user, thread_ts)
            return
        try:
            echo_ts = self._poster.post(channel, thread_ts, [to_slack.section(texts.asked_for(user, question))],
                                        texts.asked_for(user, question),
                                        metadata={"event_type": batching.QUESTION_EVENT,
                                                  "event_payload": {"user": user, "question": question}})
        except SlackApiError as exc:
            log.warning("idea not posted in %s: %s", channel, exc.response.get("error"))
            return
        self._store.record_question(user)
        self._poster.react(channel, echo_ts, EYES)
        self._queue(channel, thread_ts, direct)

    def on_assistant_thread_started(self, event: dict) -> None:
        """Slack's assistant pane: the same ideas as the app's start screen, as suggested prompts."""
        thread = event.get("assistant_thread") or {}
        channel, thread_ts = thread.get("channel_id"), thread.get("thread_ts")
        if not (channel and thread_ts):
            return
        prompts = [{"title": slack_text.shortened(question, 75), "message": question}
                   for question in starter_questions.for_page("", "es", seed=str(thread_ts))]
        try:
            self._poster.call(self._poster.client.assistant_threads_setSuggestedPrompts, channel_id=channel,
                              thread_ts=thread_ts, title=IDEAS_TITLE, prompts=prompts)
        except SlackApiError as exc:
            log.warning("suggested prompts not set in %s: %s", channel, exc.response.get("error"))

    def _take(self, *, channel: str, user: str, ts: str, thread_ts: str, text: str, has_files: bool,
              direct: bool) -> None:
        if not (channel and user and ts) or self._duplicate(channel, ts):
            return
        verdict = self._access.check(channel, user, direct)
        if verdict != Verdict.ALLOWED:
            self._refuse(channel, user, thread_ts, verdict)
            return
        if batching.is_help(slack_text.readable(text, self._access.name_of, self._identity.user_id)) and not has_files:
            self._offer_ideas(channel, thread_ts)
            return
        key = (channel, thread_ts)
        if self._over_limit(user):
            self._registry.exclude(key, ts, direct)
            self._persist(key)
            self._poster.react(channel, ts, REFUSED)
            self._limit_notice(channel, user, thread_ts)
            return
        self._store.record_question(user)
        self._poster.react(channel, ts, EYES)
        self._queue(channel, thread_ts, direct)

    def _queue(self, channel: str, thread_ts: str, direct: bool) -> None:
        key = (channel, thread_ts)
        log.info("question in %s/%s%s", channel, thread_ts, " (direct)" if direct else "")
        if self._registry.mention(channel, thread_ts, direct):
            self._scheduler.submit(key, delay=self._settings.gather_seconds)
            # Threads still gathering count too: five mentions within seconds would otherwise all look free.
            waiting = self._scheduler.waiting_behind(key)
            if waiting:
                self._say(channel, thread_ts, texts.queued(*waiting))
        self._persist(key)

    def _over_limit(self, user: str) -> bool:
        return self._store.questions_last_day(user) >= self._settings.daily_questions_per_user

    def _limit_notice(self, channel: str, user: str, thread_ts: str) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        if self._access.first_notice("limit", f"{user}:{day}"):
            self._poster.ephemeral(channel, user, texts.limit_reached(self._settings.daily_questions_per_user),
                                   thread_ts=thread_ts)

    def _refuse(self, channel: str, user: str, thread_ts: str, verdict: Verdict) -> None:
        log.info("refused %s in %s: %s", user, channel, verdict.value)
        if verdict in (Verdict.CHANNEL_NOT_ALLOWED, Verdict.CHANNEL_SHARED):
            if self._access.first_notice("channel", channel):
                self._say(channel, thread_ts, texts.CHANNEL_NOT_ALLOWED if verdict == Verdict.CHANNEL_NOT_ALLOWED
                          else texts.CHANNEL_SHARED)
        elif verdict in (Verdict.GUEST, Verdict.EXTERNAL):
            if self._access.first_notice("person", user):
                self._poster.ephemeral(channel, user, texts.NOT_A_MEMBER, thread_ts=thread_ts)
        elif verdict == Verdict.DIRECT_DISABLED and self._access.first_notice("direct", user):
            self._say(channel, thread_ts, texts.DIRECT_DISABLED)

    def _offer_ideas(self, channel: str, thread_ts: str) -> None:
        questions = starter_questions.for_page("", "es", seed=thread_ts)
        try:
            self._poster.post(channel, thread_ts, to_slack.ideas_blocks(texts.IDEAS_INTRO, questions),
                              texts.IDEAS_INTRO)
        except SlackApiError as exc:
            log.warning("ideas not posted in %s: %s", channel, exc.response.get("error"))

    def _say(self, channel: str, thread_ts: str, text: str) -> None:
        notice = to_slack.Notice.of(text)
        try:
            self._poster.post(channel, thread_ts, notice.blocks, notice.text)
        except SlackApiError as exc:
            log.warning("notice not posted in %s: %s", channel, exc.response.get("error"))

    def _persist(self, key: Key) -> None:
        snapshot = self._registry.snapshot(key)
        if snapshot is not None:
            self._store.save(snapshot)

    def _duplicate(self, channel: str, ts: str) -> bool:
        """Slack retries an event it thinks was lost, and both of its copies must count once."""
        with self._lock:
            if (channel, ts) in self._seen:
                return True
            self._seen[(channel, ts)] = None
            while len(self._seen) > _SEEN_EVENTS:
                self._seen.popitem(last=False)
            return False

    def _heard(self, event: dict) -> None:
        now = self._clock()
        if now - self._last_event_saved < _LAST_EVENT_EVERY_S:
            return
        self._last_event_saved = now
        self._store.set_meta(LAST_EVENT_TS, str(event.get("event_ts") or event.get("ts") or now))

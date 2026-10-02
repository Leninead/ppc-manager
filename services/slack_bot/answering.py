"""One cycle of a thread: read it from Slack, have the chat answer in one turn what was asked since the last
answer, post it.

Slack is the source of truth: the batch is rebuilt from the thread on every cycle, so edits, deletions and the
conversation people had without mentioning the bot all count. A turn's answers are stored with the watermark that
passes their questions, in one transaction, and posted step by step from there: a crash or a Slack outage delays
them, but never loses them and never asks the model twice. The turn itself runs in PPC Manager's chat API: this
module never touches the database or the provider.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from slack_sdk.errors import SlackApiError

from core.chat import components
from services.slack_bot import batch as batching
from services.slack_bot import texts, to_slack
from services.slack_bot.access import AccessPolicy, Verdict
from services.slack_bot.chat_client import ChatClient, ChatError, ChatOutcome, ChatQuota, SessionLost
from services.slack_bot.conversations import Conversation, ConversationRegistry, Key
from services.slack_bot.poster import SlackPoster
from services.slack_bot.scheduler import TurnScheduler
from services.slack_bot.settings import BotSettings
from services.slack_bot.state_store import StateStore

log = logging.getLogger(__name__)

MAX_FAILURES = 2
MAX_DELIVERY_ATTEMPTS = 3
FAILURE_RETRY_S = 30
EYES, DONE, SKIPPED, FAILED, REFUSED = "eyes", "white_check_mark", "ok_hand", "x", "no_entry"

_THREAD_PAGES = 5
_SLACK_PAGE = 200


@dataclass(frozen=True)
class BotIdentity:
    user_id: str
    bot_id: str
    team_id: str


class StatusLine:
    """Slack's "is thinking" line for the whole turn, naming what is being read; Slack drops it after 2 idle minutes."""

    refresh_s = 90.0
    min_gap_s = 3.0

    def __init__(self, poster: SlackPoster, channel: str, thread_ts: str, clock=time.monotonic):
        self._poster = poster
        self._channel = channel
        self._thread_ts = thread_ts
        self._clock = clock
        self._sources: list[str] = []
        self._text = texts.THINKING
        self._shown: str | None = None
        self._shown_at = float("-inf")
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def __enter__(self) -> StatusLine:
        self._show(force=True)
        threading.Thread(target=self._keep_alive, name="slack-status", daemon=True).start()
        return self

    def __exit__(self, *exc) -> bool:
        with self._lock:
            self._stop.set()
        self._poster.status(self._channel, self._thread_ts, "")
        return False

    def source(self, label: str) -> None:
        with self._lock:
            if label in self._sources:
                return
            self._sources.append(label)
            self._text = texts.reading(self._sources)
        self._show()

    def _show(self, force: bool = False) -> None:
        """Shows a changed text once `min_gap_s` passed since the last call, or refreshes it before Slack drops it."""
        with self._lock:
            now = self._clock()
            elapsed = now - self._shown_at
            due = force or (self._text != self._shown and elapsed >= self.min_gap_s) or elapsed >= self.refresh_s
            if not due or self._stop.is_set():
                return
            self._shown, self._shown_at = self._text, now
            # Inside the lock, so a status can never land after __exit__ cleared it.
            self._poster.status(self._channel, self._thread_ts, self._text,
                                texts.LOADING if self._text == texts.THINKING else None)

    def _keep_alive(self) -> None:
        # A change that came too soon after the last call waits here for its turn.
        while not self._stop.wait(max(self.min_gap_s, 0.5)):
            self._show()


class ThreadAnswerer:
    def __init__(self, *, slack, poster: SlackPoster, registry: ConversationRegistry, scheduler: TurnScheduler,
                 store: StateStore, access: AccessPolicy, settings: BotSettings, identity: BotIdentity,
                 chat: ChatClient, clock=time.time, sleep=time.sleep):
        self._slack = slack
        self._poster = poster
        self._registry = registry
        self._scheduler = scheduler
        self._store = store
        self._access = access
        self._settings = settings
        self._identity = identity
        self._chat = chat
        self._clock = clock
        self._sleep = sleep

    def handle(self, key: Key) -> None:
        conversation = self._registry.start(key)
        if conversation is None:
            return
        try:
            self._cycle(conversation)
        except Exception as exc:  # whatever breaks, the thread must hear about it and leave the answering stage
            log.exception("thread %s/%s failed", *key)
            self._failed(conversation, None, type(exc).__name__, retry_s=FAILURE_RETRY_S)

    def read_thread(self, channel: str, thread_ts: str, oldest: str | None = None) -> list[batching.ThreadMessage]:
        raw: list[dict] = []
        cursor = None
        for _ in range(_THREAD_PAGES):
            extra = {"cursor": cursor} if cursor else {}
            if oldest and oldest != "0":
                extra.update(oldest=oldest, inclusive=True)
            response = self._poster.call(self._slack.conversations_replies, channel=channel, ts=thread_ts,
                                         limit=_SLACK_PAGE, include_all_metadata=True, **extra)
            raw.extend(response.get("messages") or [])
            cursor = (response.get("response_metadata") or {}).get("next_cursor")
            if not (response.get("has_more") and cursor):
                break
        return [batching.ThreadMessage.from_slack(message, self._identity.user_id, self._identity.bot_id)
                for message in raw]

    def deliver_pending(self, key: Key) -> bool:
        """Posts what is left of a stored turn; False when a step failed and the rest has to wait."""
        pending = self._store.pending_delivery(key)
        if pending is None:
            return True
        payload, done, _ = pending
        steps = self._steps(key, payload)
        for index in range(done, len(steps)):
            try:
                steps[index]()
            except Exception:  # a step that keeps failing is given up, the answers before it already went out
                log.exception("delivery step %d of %s/%s failed", index, *key)
                if self._store.delivery_failed(key) >= MAX_DELIVERY_ATTEMPTS:
                    log.error("delivery of %s/%s dropped after %d attempts", *key, MAX_DELIVERY_ATTEMPTS)
                    self._store.drop_delivery(key)
                    return True
                return False
            self._store.delivery_step_done(key, index + 1)
        self._store.drop_delivery(key)
        return True

    def _cycle(self, conversation: Conversation) -> None:
        key = conversation.key
        if not self.deliver_pending(key):
            self._settle(key, self._registry.finish(key), delay=FAILURE_RETRY_S, force=True)
            return
        if not conversation.direct:
            place = self._access.check_place(conversation.channel, False, fresh=True)
            if place == Verdict.UNKNOWN:
                self._failed(conversation, None, "no pude verificar el canal", retry_s=FAILURE_RETRY_S)
                return
            if place != Verdict.ALLOWED:
                self._close(conversation, place)
                return

        oldest = min([conversation.watermark, *conversation.carried], key=batching.ts_value)
        messages = self.read_thread(conversation.channel, conversation.thread_ts, oldest)
        batch = batching.build_batch(
            messages, watermark=conversation.watermark, carried=conversation.carried.keys(),
            excluded=conversation.excluded, bot_user_id=self._identity.user_id, direct=conversation.direct,
            name_of=self._access.name_of, max_questions=self._settings.batch_max_questions,
            max_chars=self._settings.batch_max_chars,
            may_ask=lambda user: self._access.check_person(user) == Verdict.ALLOWED)
        included = {question.ts for question in batch.questions} if batch else set()
        vanished = [ts for ts in conversation.carried if ts not in included]
        if batch is None:
            for ts in vanished:
                self._swap(conversation.channel, ts, FAILED)
            self._settle(key, self._registry.finish(key, carried={}))
            return

        with StatusLine(self._poster, conversation.channel, conversation.thread_ts) as status:
            try:
                outcome = self._ask(conversation, batch, status.source)
            except ChatQuota as exc:
                self._failed(conversation, batch, str(exc), retry_s=max(int(exc.retry_after), 1), quota=True)
                return
            except ChatError as exc:
                self._failed(conversation, batch, str(exc), retry_s=FAILURE_RETRY_S)
                return
        self._answered(conversation, batch, outcome, vanished)

    def _ask(self, conversation: Conversation, batch: batching.Batch,
             on_source: Callable[[str], None]) -> ChatOutcome:
        """The chat's answer; a session that cannot be resumed is opened again with the thread so far as history."""
        session_id = conversation.session_to_resume(self._clock())
        payload = self._payload(conversation, batch, session_id)
        if session_id:
            try:
                return self._chat.turn(payload, on_source)
            except SessionLost as exc:
                log.warning("session of %s/%s not resumed (%s); opening a new one", *conversation.key, exc)
        fresh = self._payload(conversation, batch, None)
        history = self._history(conversation)
        if history:
            fresh["history"] = history
        return self._chat.turn(fresh, on_source)

    def _payload(self, conversation: Conversation, batch: batching.Batch, session_id: str | None) -> dict:
        askers = list(dict.fromkeys(question.user for question in batch.questions))
        account = self._settings.channel_accounts.get(conversation.channel)
        return {
            "conversation": f"slack:{conversation.channel}:{conversation.thread_ts}",
            "prompt": batch.prompt(),
            "question_ids": batch.question_ids,
            "questions": [{"asker": self._access.name_of(q.user), "text": q.text} for q in batch.questions],
            "place": {"direct": conversation.direct,
                      "channel_name": "" if conversation.direct else self._access.channel_name(conversation.channel),
                      "client": account.client if account else "", "country": account.country if account else ""},
            "requested_by": "slack:" + ", ".join(self._access.name_of(user) for user in askers),
            "session_id": session_id,
            "session_region": conversation.region if session_id else None,
            "effort": self._settings.effort,
        }

    def _history(self, conversation: Conversation) -> dict | None:
        if conversation.watermark == "0":
            return None
        return batching.history_document(self.read_thread(conversation.channel, conversation.thread_ts),
                                         before_ts=conversation.watermark, bot_user_id=self._identity.user_id,
                                         name_of=self._access.name_of)

    def _answered(self, conversation: Conversation, batch: batching.Batch, outcome: ChatOutcome,
                  vanished: list[str]) -> None:
        key = conversation.key
        by_id = {question.id: question for question in batch.questions}
        carried: dict[str, int] = {}
        dropped = []
        for ident in outcome.reply.missing:
            if ident not in by_id:
                continue
            if by_id[ident].ts in conversation.carried:
                dropped.append(ident)
            else:
                carried[by_id[ident].ts] = 1
        again = self._registry.finish(key, watermark=batch.until_ts, session_id=outcome.session_id,
                                      region=outcome.region, new_session=outcome.new_session, carried=carried,
                                      still_owed=batch.left_for_next > 0)
        self._persist(key, delivery={
            "direct": conversation.direct, "first_turn": conversation.watermark == "0",
            "questions": [{"id": q.id, "ts": q.ts, "user": q.user, "text": q.text} for q in batch.questions],
            "answers": [{"question_ids": list(a.question_ids), "blocks": a.blocks} for a in outcome.reply.answers],
            "skipped": sorted(outcome.reply.skipped), "dropped": dropped, "vanished": vanished,
            "left_for_next": batch.left_for_next,
            "sources": list(outcome.sources), "failed_sources": list(outcome.failed_sources)})
        log.info("answered %s/%s: %d question(s), %d answer(s) [%s], %d skipped, %d unanswered, tools %s, cost %s",
                 *key, len(batch.questions), len(outcome.reply.answers),
                 " | ".join("+".join(block.get("kind", "?") for block in answer.blocks)
                            for answer in outcome.reply.answers),
                 len(outcome.reply.skipped), len(outcome.reply.missing), outcome.tool_count, outcome.cost_usd)
        if not self.deliver_pending(key):
            self._scheduler.submit(key, delay=FAILURE_RETRY_S)
        elif again:
            self._scheduler.submit(key)

    def _steps(self, key: Key, payload: dict) -> list[Callable[[], None]]:
        """Every post and reaction of a stored turn, in order; the same payload always gives the same steps."""
        channel, _ = key
        questions = {question["id"]: question for question in payload["questions"]}
        sources = texts.sources(list(payload.get("sources") or ()), list(payload.get("failed_sources") or ()))
        answers = payload["answers"]
        steps: list[Callable[[], None]] = []
        for index, answer in enumerate(answers):
            asked = [questions[ident] for ident in answer["question_ids"] if ident in questions]
            mentions = [f"<@{user}>" for user in dict.fromkeys(question["user"] for question in asked)]
            # The chat API is another process: its blocks are validated again before anything is drawn.
            blocks = components.normalize({"blocks": answer["blocks"]}) or []
            parts = to_slack.answer_parts(
                blocks, header=texts.answer_header(mentions, [question["text"] for question in asked]),
                sources=sources if index == 0 else "", mention=" ".join(mentions))
            if payload["first_turn"] and index == len(answers) - 1:
                _append_hint(parts, texts.keep_going(payload["direct"]))
            steps += [partial(self._post_part, key, part) for part in parts]

        answered = {ident for answer in answers for ident in answer["question_ids"]}
        for question in payload["questions"]:
            if question["id"] in answered:
                steps.append(partial(self._swap, channel, question["ts"], DONE))
            elif question["id"] in payload["skipped"]:
                steps.append(partial(self._swap, channel, question["ts"], SKIPPED))
            elif question["id"] in payload["dropped"]:
                steps.append(partial(self._swap, channel, question["ts"], FAILED))
                steps.append(partial(self._notice, key, texts.not_answered(question["text"])))
        steps += [partial(self._swap, channel, ts, FAILED) for ts in payload["vanished"]]
        if payload["left_for_next"]:
            steps.append(partial(self._notice, key, texts.more_than_fit(payload["left_for_next"])))
        return steps

    def _failed(self, conversation: Conversation, batch: batching.Batch | None, error: str, *, retry_s: int,
                quota: bool = False) -> None:
        key = conversation.key
        if conversation.failures + 1 > MAX_FAILURES:
            again = self._registry.give_up(key, batch.until_ts if batch else conversation.watermark)
            self._persist(key)
            self._notice(key, texts.gave_up(error))
            for question in batch.questions if batch else ():
                self._swap(conversation.channel, question.ts, FAILED)
            if again:
                self._scheduler.submit(key)
            return
        self._registry.finish(key, failed=True)
        self._persist(key)
        self._notice(key, texts.quota_retry(retry_s) if quota else texts.failure_retry(error, retry_s))
        self._scheduler.submit(key, delay=retry_s)

    def _close(self, conversation: Conversation, place: Verdict) -> None:
        """The channel stopped being a place to answer (shared outside since the mention): drop what it asked."""
        key = conversation.key
        latest = max([message.ts for message in self.read_thread(*key, conversation.watermark)]
                     + [conversation.watermark], key=batching.ts_value)
        self._registry.close(key, latest)
        self._persist(key)
        log.warning("thread %s/%s closed: %s", *key, place.value)
        if place == Verdict.CHANNEL_SHARED and self._access.first_notice("channel", conversation.channel):
            self._notice(key, texts.CHANNEL_SHARED)

    def _settle(self, key: Key, again: bool, delay: float = 0.0, force: bool = False) -> None:
        self._persist(key)
        if again or force:
            self._scheduler.submit(key, delay=delay)

    def _persist(self, key: Key, delivery: dict | None = None) -> None:
        snapshot = self._registry.snapshot(key)
        if snapshot is not None:
            self._store.save(snapshot, delivery)

    def _post_part(self, key: Key, part: to_slack.Part) -> None:
        """A part refused by Slack is tried once more as plain text, so the answer still lands."""
        channel, thread_ts = key
        try:
            self._poster.post_part(channel, thread_ts, part)
            return
        except SlackApiError as exc:
            log.warning("part refused by Slack (%s); sending it as text", exc.response.get("error"))
        self._sleep(2)
        text = part.text if isinstance(part, to_slack.MessagePart) else f"{part.title}\n{part.alt}"
        try:
            self._poster.post(channel, thread_ts, to_slack.prose(text), text)
        except SlackApiError as exc:
            log.error("part dropped in %s/%s: %s", channel, thread_ts, exc.response.get("error"))

    def _notice(self, key: Key, text: str) -> None:
        notice = to_slack.Notice.of(text)
        try:
            self._poster.post(*key, notice.blocks, notice.text)
        except SlackApiError as exc:
            log.warning("notice not posted in %s/%s: %s", *key, exc.response.get("error"))

    def _swap(self, channel: str, ts: str, reaction: str) -> None:
        self._poster.unreact(channel, ts, EYES)
        self._poster.react(channel, ts, reaction)


def _append_hint(parts: list[to_slack.Part], hint: str) -> None:
    last = parts[-1] if parts else None
    if isinstance(last, to_slack.MessagePart) and len(last.blocks) < 45:
        last.blocks.append(to_slack.context(hint))
    else:
        parts.append(to_slack.MessagePart([to_slack.context(hint)], hint))

"""Everything the bot writes to Slack, paced to its limits: about one message per second per channel."""
from __future__ import annotations

import logging
import threading
import time

from slack_sdk.errors import SlackApiError

from services.slack_bot.to_slack import ChartPart, MessagePart, Part

log = logging.getLogger(__name__)

_RATE_LIMIT_RETRIES = 3
_MAX_RETRY_WAIT_S = 30
# Slack answers these when a reaction is already in the state asked for: nothing to do.
_HARMLESS_REACTION_ERRORS = frozenset({"already_reacted", "no_reaction", "message_not_found"})


class SlackPoster:
    def __init__(self, client, clock=time.monotonic, sleep=time.sleep, interval_s: float = 1.1):
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self._interval = interval_s
        self._last_post: dict[str, float] = {}
        self._lock = threading.Lock()
        self._status_works = True

    @property
    def client(self):
        return self._client

    def post(self, channel: str, thread_ts: str, blocks: list[dict], text: str, metadata: dict | None = None) -> str:
        """The message's ts. Raises SlackApiError when Slack refuses it even after waiting out its rate limit."""
        self._pace(channel)
        response = self.call(self._client.chat_postMessage, channel=channel, thread_ts=thread_ts, blocks=blocks,
                              text=text, metadata=metadata, unfurl_links=False, unfurl_media=False)
        return str(response["ts"])

    def post_part(self, channel: str, thread_ts: str, part: Part) -> None:
        if isinstance(part, MessagePart):
            self.post(channel, thread_ts, part.blocks, part.text)
        elif isinstance(part, ChartPart):
            self._pace(channel)
            self.call(self._client.files_upload_v2, channel=channel, thread_ts=thread_ts, file=part.png,
                       filename="grafico.png", title=part.title, alt_txt=part.alt[:1000])

    def ephemeral(self, channel: str, user: str, text: str, thread_ts: str | None = None) -> None:
        try:
            self.call(self._client.chat_postEphemeral, channel=channel, user=user, text=text, thread_ts=thread_ts)
        except SlackApiError as exc:
            log.warning("ephemeral to %s in %s refused: %s", user, channel, exc.response.get("error"))

    def react(self, channel: str, ts: str, name: str) -> None:
        self._reaction(self._client.reactions_add, channel, ts, name)

    def unreact(self, channel: str, ts: str, name: str) -> None:
        self._reaction(self._client.reactions_remove, channel, ts, name)

    def status(self, channel: str, thread_ts: str, text: str, loading: list[str] | None = None) -> None:
        """Slack's own "is thinking" line under the thread; it clears itself with the next message or in 2 min."""
        if not self._status_works:
            return
        try:
            self._client.assistant_threads_setStatus(channel_id=channel, thread_ts=thread_ts, status=text,
                                                     loading_messages=loading or None)
        except SlackApiError as exc:
            error = exc.response.get("error")
            if error == "ratelimited":
                return
            # Without the AI app feature Slack may refuse it: the reactions carry the progress instead.
            log.warning("thread status unavailable (%s); progress shows only as reactions", error)
            self._status_works = False

    def _reaction(self, method, channel: str, ts: str, name: str) -> None:
        try:
            self.call(method, channel=channel, timestamp=ts, name=name)
        except SlackApiError as exc:
            if exc.response.get("error") not in _HARMLESS_REACTION_ERRORS:
                log.warning("reaction %s on %s/%s failed: %s", name, channel, ts, exc.response.get("error"))

    def _pace(self, channel: str) -> None:
        with self._lock:
            wait = self._last_post.get(channel, float("-inf")) + self._interval - self._clock()
            self._last_post[channel] = self._clock() + max(wait, 0)
        if wait > 0:
            self._sleep(wait)

    def call(self, method, **kwargs):
        """Calls a Slack method, waiting out its rate limit a few times before giving up."""
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            try:
                return method(**kwargs)
            except SlackApiError as exc:
                if exc.response.get("error") != "ratelimited" or attempt == _RATE_LIMIT_RETRIES:
                    raise
                self._sleep(min(max(_seconds(exc.response.headers.get("Retry-After")), 1), _MAX_RETRY_WAIT_S))
        raise RuntimeError("unreachable")


def _seconds(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0

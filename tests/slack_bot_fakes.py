"""A Slack workspace in memory for the bot's tests: threads, members, channels and everything the bot writes."""
from __future__ import annotations

from decimal import Decimal

from slack_sdk.errors import SlackApiError

from services.slack_bot.answering import BotIdentity
from services.slack_bot.batch_reply import BatchAnswer, BatchReply
from services.slack_bot.turn import TurnOutcome

BOT = BotIdentity(user_id="UBOT", bot_id="BBOT", team_id="T1")
MEMBERS = {
    "U1": {"profile": {"display_name": "Lenin"}, "team_id": "T1"},
    "U2": {"profile": {"display_name": "Marcos"}, "team_id": "T1"},
    "U3": {"profile": {"display_name": "Ana"}, "team_id": "T1"},
    "UGUEST": {"profile": {"display_name": "Invitado"}, "team_id": "T1", "is_restricted": True},
    "UEXT": {"profile": {"display_name": "Cliente"}, "team_id": "TOTHER"},
}
CHANNELS = {"CPPC": {"name": "ppc-ltd"}, "COTHER": {"name": "random"},
            "CSHARED": {"name": "con-cliente", "is_ext_shared": True}}


class _Response(dict):
    headers: dict = {}


class FakeSlack:
    def __init__(self):
        self.threads: dict[tuple[str, str], list[dict]] = {}
        self.history: dict[str, list[dict]] = {}
        self.posted: list[dict] = []
        self.uploads: list[dict] = []
        self.ephemerals: list[dict] = []
        self.reactions: list[tuple[str, str, str, str]] = []
        self.statuses: list[dict] = []
        self.prompts: list[dict] = []
        self.refuse_posts_with: str | None = None
        self.member_of: list[dict] = []
        self._clock = 2000

    def add(self, channel: str, thread_ts: str, ts: str, user: str, text: str, **extra) -> dict:
        message = {"ts": ts, "user": user, "text": text, **extra}
        if ts != thread_ts:
            message["thread_ts"] = thread_ts
        self.threads.setdefault((channel, thread_ts), []).append(message)
        return message

    def conversations_replies(self, *, channel, ts, limit, include_all_metadata, cursor=None, oldest=None,
                              inclusive=None):
        messages = sorted(self.threads.get((channel, ts), []), key=lambda m: Decimal(m["ts"]))
        if oldest:
            messages = [m for m in messages if Decimal(m["ts"]) >= Decimal(oldest)]
        return _Response(messages=messages, has_more=False)

    def conversations_history(self, *, channel, oldest, limit, cursor=None):
        return _Response(messages=[m for m in self.history.get(channel, []) if Decimal(m["ts"]) > Decimal(oldest)],
                         has_more=False)

    def chat_postMessage(self, *, channel, thread_ts, blocks, text, metadata=None, **_):
        if self.refuse_posts_with and blocks and blocks[0].get("type") != "section":
            raise SlackApiError("refused", _Response(ok=False, error=self.refuse_posts_with))
        self._clock += 1
        ts = f"{self._clock}.000"
        message = {"ts": ts, "user": BOT.user_id, "bot_id": BOT.bot_id, "text": text}
        if metadata:
            message["metadata"] = metadata
        self.threads.setdefault((channel, thread_ts), []).append({**message, "thread_ts": thread_ts})
        self.posted.append({"channel": channel, "thread_ts": thread_ts, "blocks": blocks, "text": text,
                            "metadata": metadata, "ts": ts})
        return _Response(ts=ts)

    def files_upload_v2(self, **kwargs):
        self.uploads.append(kwargs)
        return _Response(ok=True)

    def chat_postEphemeral(self, **kwargs):
        self.ephemerals.append(kwargs)
        return _Response(ok=True)

    def reactions_add(self, *, channel, timestamp, name):
        self.reactions.append(("add", channel, timestamp, name))
        return _Response(ok=True)

    def reactions_remove(self, *, channel, timestamp, name):
        self.reactions.append(("remove", channel, timestamp, name))
        return _Response(ok=True)

    def assistant_threads_setStatus(self, **kwargs):
        self.statuses.append(kwargs)
        return _Response(ok=True)

    def assistant_threads_setSuggestedPrompts(self, **kwargs):
        self.prompts.append(kwargs)
        return _Response(ok=True)

    def users_info(self, *, user):
        if user not in MEMBERS:
            raise SlackApiError("user_not_found", _Response(ok=False, error="user_not_found"))
        return _Response(user={"id": user, **MEMBERS[user]})

    def users_conversations(self, **kwargs):
        return _Response(channels=self.member_of)

    def conversations_info(self, *, channel):
        return _Response(channel=CHANNELS.get(channel, {"name": channel}))

    def added(self, ts: str) -> list[str]:
        return [name for kind, _, stamp, name in self.reactions if kind == "add" and stamp == ts]

    def texts(self) -> list[str]:
        return [post["text"] for post in self.posted]


def text_answer(question_ids, text):
    return BatchAnswer(tuple(question_ids), [{"kind": "text", "text": text}])


def outcome(*answers, skipped=None, missing=(), session_id="S1", tools=("mcp__ppc_manager__daily_metrics",)):
    return TurnOutcome(reply=BatchReply(tuple(answers), skipped or {}, tuple(missing)), session_id=session_id,
                       tool_calls=tuple(tools), failed_tools=(), model="claude-opus-5-5", cost_usd=0.42)


class FakeScheduler:
    def __init__(self, waiting=None):
        self.submitted: list[tuple[tuple[str, str], float]] = []
        self.waiting = waiting

    def submit(self, key, delay=0.0):
        self.submitted.append((key, delay))

    def waiting_behind(self, key):
        return self.waiting


class TurnScript:
    """Plays the provider: one scripted outcome or exception per call, and remembers what each call asked."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["on_tool"]("mcp__amazon_ads__campaign_management-query_campaign", None)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

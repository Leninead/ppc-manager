"""What one turn answers: the questions asked since the last answer, and the conversation around them."""
from __future__ import annotations

import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from services.slack_bot import slack_text

# Our own echo of an idea someone clicked: a question asked in their name.
QUESTION_EVENT = "capybaras_question"
HISTORY_TITLE = "Conversación previa de este hilo de Slack"
# The echo's own text, read when Slack does not hand the metadata back.
_ECHO_TEXT = re.compile(r"^<@([UW][A-Z0-9]+)> preguntó: (.+)$", re.S)
ASSISTANT_NAME = "Asistente"

_HELP_WORDS = frozenset({"", "ayuda", "help", "ideas", "hola"})
_QUESTION_CHARS = 1200
_CONTEXT_CHARS = 800
_HISTORY_MESSAGES = 30
_HISTORY_CHARS = 12_000


def ts_value(ts: str) -> Decimal:
    try:
        return Decimal(ts or "0")
    except InvalidOperation:
        return Decimal(0)


def is_help(text: str) -> bool:
    """A mention with nothing to answer: the bot offers ideas instead of a turn."""
    return text.strip().lower().strip("¿?¡!.,;: ") in _HELP_WORDS


@dataclass(frozen=True)
class ThreadMessage:
    ts: str
    user: str
    text: str
    files: tuple[str, ...] = ()
    from_bot: bool = False
    from_us: bool = False
    asked_by: str = ""
    asked_text: str = ""

    @classmethod
    def from_slack(cls, raw: dict, bot_user_id: str, bot_id: str) -> ThreadMessage:
        metadata = raw.get("metadata") or {}
        payload = metadata.get("event_payload") or {}
        from_us = bool(bot_id and raw.get("bot_id") == bot_id) or bool(bot_user_id and raw.get("user") == bot_user_id)
        text = str(raw.get("text") or "")
        asked_by = asked_text = ""
        if from_us and metadata.get("event_type") == QUESTION_EVENT:
            asked_by, asked_text = str(payload.get("user") or ""), str(payload.get("question") or "")
        elif from_us and (match := _ECHO_TEXT.match(text)):
            asked_by, asked_text = match.group(1), slack_text.readable(match.group(2), lambda user: user)
        return cls(ts=str(raw.get("ts") or ""), user=str(raw.get("user") or ""), text=text,
                   files=tuple(str(f.get("name") or f.get("title") or "archivo") for f in raw.get("files") or ()
                               if isinstance(f, dict)),
                   from_bot=from_us or bool(raw.get("bot_id")) or raw.get("subtype") == "bot_message",
                   from_us=from_us, asked_by=asked_by, asked_text=asked_text)


@dataclass(frozen=True)
class Question:
    id: str
    ts: str
    user: str
    text: str


@dataclass(frozen=True)
class Batch:
    questions: tuple[Question, ...]
    lines: tuple[str, ...]
    until_ts: str
    left_for_next: int = 0
    omitted_context: int = 0

    @property
    def question_ids(self) -> list[str]:
        return [question.id for question in self.questions]

    def prompt(self) -> str:
        head = ("Mensajes del hilo desde tu última respuesta, en orden. Los que empiezan con un id (q1, q2…) te "
                "mencionan: son las preguntas. Los demás son la conversación entre ellos: son contexto y no se "
                "contestan.")
        omitted = ([f"(Antes de estos hubo {self.omitted_context} mensajes más de la conversación, que no entran acá.)"]
                   if self.omitted_context else [])
        return "\n".join([head, *omitted, *self.lines])


def asked(message: ThreadMessage, *, bot_user_id: str, direct: bool,
          name_of: Callable[[str], str]) -> tuple[str, str] | None:
    """(who, what) when the message asks the bot something, else None."""
    if message.from_us:
        return (message.asked_by, message.asked_text) if message.asked_by and message.asked_text.strip() else None
    if message.from_bot or not message.user:
        return None
    if not direct and not slack_text.mentions(message.text, bot_user_id):
        return None
    text = slack_text.readable(message.text, name_of, bot_user_id)
    return None if is_help(text) and not message.files else (message.user, text)


def build_batch(messages: Sequence[ThreadMessage], *, watermark: str, carried: Collection[str] = (),
                excluded: Collection[str] = (), bot_user_id: str, direct: bool, name_of: Callable[[str], str],
                max_questions: int, max_chars: int,
                may_ask: Callable[[str], bool] = lambda user: True) -> Batch | None:
    """The oldest questions not yet answered, up to `max_questions`, with what was said around them.

    `carried` are questions a previous turn left unanswered, read again even though the watermark passed them;
    `excluded` are mentions refused at the door, shown as conversation and never answered. Messages of people
    who may not ask (a guest in an allowed channel) stay out entirely, not even as conversation.
    """
    def by_member(message: ThreadMessage) -> bool:
        if message.asked_by:
            return may_ask(message.asked_by)
        return not message.from_bot and bool(message.user) and may_ask(message.user)

    floor = ts_value(watermark)
    pending = sorted((m for m in messages if (ts_value(m.ts) > floor or m.ts in carried) and by_member(m)),
                     key=lambda m: ts_value(m.ts))
    window: list[tuple[ThreadMessage, tuple[str, str] | None]] = []
    count = 0
    left = 0
    for index, message in enumerate(pending):
        question = None if message.ts in excluded else asked(message, bot_user_id=bot_user_id, direct=direct,
                                                             name_of=name_of)
        if question and count >= max_questions:
            left = sum(1 for later in pending[index:]
                       if later.ts not in excluded
                       and asked(later, bot_user_id=bot_user_id, direct=direct, name_of=name_of))
            break
        window.append((message, question))
        count += 1 if question else 0
    if not count:
        return None

    questions: list[Question] = []
    entries: list[tuple[bool, str]] = []
    for message, question in window:
        if question:
            ident = f"q{len(questions) + 1}"
            text = (slack_text.shortened(question[1], _QUESTION_CHARS) + _attachments(message)).strip()
            questions.append(Question(ident, message.ts, question[0], text))
            entries.append((True, f"{ident} · {name_of(question[0])}: {text}"))
        elif not message.from_bot and message.user:
            text = slack_text.shortened(slack_text.readable(message.text, name_of, bot_user_id), _CONTEXT_CHARS)
            if text or message.files:
                entries.append((False, f"{name_of(message.user)}: {text}{_attachments(message)}".rstrip()))

    omitted = 0
    while sum(len(line) + 1 for _, line in entries) > max_chars:
        oldest_context = next((i for i, (is_question, _) in enumerate(entries) if not is_question), None)
        if oldest_context is None:
            break
        entries.pop(oldest_context)
        omitted += 1
    until = max((message.ts for message, _ in window), key=ts_value)
    return Batch(questions=tuple(questions), lines=tuple(line for _, line in entries),
                 until_ts=max(until, watermark, key=ts_value), left_for_next=left, omitted_context=omitted)


def history_document(messages: Sequence[ThreadMessage], *, before_ts: str, bot_user_id: str,
                     name_of: Callable[[str], str]) -> dict | None:
    """What was said in the thread before, for a session that has to start over."""
    floor = ts_value(before_ts)
    lines = []
    for message in sorted((m for m in messages if ts_value(m.ts) <= floor), key=lambda m: ts_value(m.ts)):
        if message.from_us:
            if message.asked_by:
                lines.append(f"{name_of(message.asked_by)}: {message.asked_text}")
            elif message.text.strip():
                lines.append(f"{ASSISTANT_NAME}: {slack_text.readable(message.text, name_of, bot_user_id)}")
        elif not message.from_bot and message.user:
            text = slack_text.readable(message.text, name_of, bot_user_id)
            if text:
                lines.append(f"{name_of(message.user)}: {text}")
    kept, used = [], 0
    for line in reversed(lines[-_HISTORY_MESSAGES:]):
        if kept and used + len(line) > _HISTORY_CHARS:
            break
        kept.append(line[:_HISTORY_CHARS])
        used += len(line) + 1
    if not kept:
        return None
    return {"title": HISTORY_TITLE, "content": "\n".join(reversed(kept))}


def _attachments(message: ThreadMessage) -> str:
    return f" [adjuntó: {', '.join(message.files)}]" if message.files else ""

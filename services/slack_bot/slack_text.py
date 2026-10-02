"""Slack's message markup in both directions: what people wrote, as the model reads it, and answers as mrkdwn."""
from __future__ import annotations

import re
from collections.abc import Callable

SECTION_LIMIT = 2900  # Slack refuses a section over 3000 characters

_USER_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
_CHANNEL = re.compile(r"<#([CGD][A-Z0-9]+)(?:\|([^>]*))?>")
_SPECIAL = re.compile(r"<!([a-z]+)(?:\^[^|>]*)?(?:\|([^>]*))?>")
_LINK = re.compile(r"<((?:https?|mailto):[^|>]+)(?:\|([^>]+))?>")
_MODEL_BOLD = re.compile(r"\*\*([^\n]+?)\*\*")
_SPACES = re.compile(r"[ \t]+")


def is_direct_channel(channel: str) -> bool:
    """Slack gives one-to-one DMs ids that start with D."""
    return channel.startswith("D")


def mentions(text: str, user_id: str) -> bool:
    return bool(user_id) and f"<@{user_id}" in (text or "")


def readable(text: str, name_of: Callable[[str], str], bot_user_id: str = "") -> str:
    """Slack's raw text as a person reads it: names instead of ids, labels instead of link markup."""
    def user(match: re.Match) -> str:
        return "" if match.group(1) == bot_user_id else f"@{name_of(match.group(1))}"

    def channel(match: re.Match) -> str:
        return f"#{match.group(2) or match.group(1)}"

    def special(match: re.Match) -> str:
        return match.group(2) or f"@{match.group(1)}"

    def link(match: re.Match) -> str:
        url, label = match.group(1), match.group(2)
        return f"{label} ({url})" if label and label != url else url

    text = _USER_MENTION.sub(user, text or "")
    text = _CHANNEL.sub(channel, text)
    text = _SPECIAL.sub(special, text)
    text = _LINK.sub(link, text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_mrkdwn(text: str) -> str:
    """The chat's prose rules (**bold** and "- " bullets) in Slack's markup, with everything else inert."""
    safe = _MODEL_BOLD.sub(lambda match: f"*{match.group(1).strip()}*", escape(text))
    lines = [f"• {line[2:]}" if line.startswith("- ") else line for line in safe.split("\n")]
    return "\n".join(lines).strip()


def quoted(mrkdwn: str) -> str:
    return "\n".join(f">{line}" if line else ">" for line in mrkdwn.split("\n"))


def sections(mrkdwn: str, limit: int = SECTION_LIMIT) -> list[str]:
    """Pieces under Slack's section limit, cut between paragraphs, then lines, then anywhere."""
    pieces: list[str] = []
    current = ""
    for paragraph in mrkdwn.split("\n\n"):
        for chunk in _fit(paragraph, limit):
            joined = f"{current}\n\n{chunk}" if current else chunk
            if len(joined) <= limit:
                current = joined
                continue
            pieces.append(current)
            current = chunk
    if current:
        pieces.append(current)
    return [piece for piece in pieces if piece.strip()]


def _fit(paragraph: str, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]
    chunks, current = [], ""
    for line in paragraph.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        joined = f"{current}\n{line}" if current else line
        if len(joined) <= limit:
            current = joined
        else:
            chunks.append(current)
            current = line
    if current:
        chunks.append(current)
    return chunks


def shortened(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: max(limit - 1, 0)].rstrip() + "…"

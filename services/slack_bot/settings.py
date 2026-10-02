"""What the bot reads from the environment, read once at startup."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

EVERY_CHANNEL = "*"


@dataclass(frozen=True)
class ChannelAccount:
    """The client a channel is about: questions that name no account are about this one."""

    client: str
    country: str = ""


@dataclass(frozen=True)
class BotSettings:
    bot_token: str = ""
    app_token: str = ""
    allowed_channels: frozenset[str] = frozenset()
    channel_accounts: Mapping[str, ChannelAccount] = field(default_factory=dict)
    allow_direct_messages: bool = True
    max_parallel_turns: int = 2
    batch_max_questions: int = 8
    batch_max_chars: int = 12_000
    gather_seconds: float = 3.0
    daily_questions_per_user: int = 40
    effort: str | None = None
    state_path: Path = Path("data/slack_bot/state.sqlite3")
    recovery_hours: float = 12.0

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.app_token)

    @property
    def every_channel(self) -> bool:
        """`SLACK_ALLOWED_CHANNELS=*`: any internal channel the bot was invited to."""
        return EVERY_CHANNEL in self.allowed_channels

    def allows_channel(self, channel: str) -> bool:
        return self.every_channel or channel in self.allowed_channels

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> BotSettings:
        defaults = cls()
        return cls(
            bot_token=env.get("SLACK_BOT_TOKEN", "").strip(),
            app_token=env.get("SLACK_APP_TOKEN", "").strip(),
            allowed_channels=frozenset(_csv(env.get("SLACK_ALLOWED_CHANNELS", ""))),
            channel_accounts=_channel_accounts(env.get("SLACK_CHANNEL_ACCOUNTS", "")),
            allow_direct_messages=_flag(env.get("SLACK_ALLOW_DIRECT_MESSAGES"), defaults.allow_direct_messages),
            max_parallel_turns=_positive_int(env, "SLACK_MAX_PARALLEL_TURNS", defaults.max_parallel_turns),
            batch_max_questions=_positive_int(env, "SLACK_BATCH_MAX_QUESTIONS", defaults.batch_max_questions),
            batch_max_chars=_positive_int(env, "SLACK_BATCH_MAX_CHARS", defaults.batch_max_chars),
            gather_seconds=_non_negative_float(env, "SLACK_GATHER_SECONDS", defaults.gather_seconds),
            daily_questions_per_user=_positive_int(env, "SLACK_DAILY_QUESTIONS_PER_USER",
                                                   defaults.daily_questions_per_user),
            effort=env.get("SLACK_EFFORT", "").strip() or None,
            state_path=Path(env.get("SLACK_STATE_PATH", "").strip() or defaults.state_path),
            recovery_hours=_non_negative_float(env, "SLACK_RECOVERY_HOURS", defaults.recovery_hours),
        )


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _flag(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in ("0", "false", "no")


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        log.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    return value if value > 0 else default


def _non_negative_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        log.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    return value if value >= 0 else default


def _channel_accounts(raw: str) -> dict[str, ChannelAccount]:
    """`{"C0123": {"client": "Love To Dream", "country": "MX"}}`; a broken value maps no channel."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        log.warning("SLACK_CHANNEL_ACCOUNTS is not valid JSON; no channel has an account")
        return {}
    if not isinstance(parsed, dict):
        return {}
    accounts = {}
    for channel, value in parsed.items():
        if isinstance(value, dict) and str(value.get("client") or "").strip():
            accounts[str(channel)] = ChannelAccount(client=str(value["client"]).strip(),
                                                    country=str(value.get("country") or "").strip().upper())
    return accounts

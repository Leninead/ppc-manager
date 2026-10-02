"""Who may ask and where: the MCP reads every client with one service token, so the perimeter is here.

Only allowed internal channels and direct messages, only members of the agency's own workspace: never a guest,
never a channel shared with another organization, where a client could ask about another client.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum

from slack_sdk.errors import SlackApiError

from services.slack_bot.settings import BotSettings

log = logging.getLogger(__name__)

_CACHE_S = 3600
_MEMBER_PAGES = 5


class Verdict(str, Enum):
    ALLOWED = "allowed"
    CHANNEL_NOT_ALLOWED = "channel_not_allowed"
    CHANNEL_SHARED = "channel_shared"
    DIRECT_DISABLED = "direct_disabled"
    GUEST = "guest"
    EXTERNAL = "external"
    BOT = "bot"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    team_id: str
    is_bot: bool
    is_guest: bool


class AccessPolicy:
    def __init__(self, client, settings: BotSettings, team_id: str, clock=time.monotonic):
        self._client = client
        self._settings = settings
        self._team_id = team_id
        self._clock = clock
        self._members: dict[str, tuple[float, Member | None]] = {}
        self._channels: dict[str, tuple[float, dict | None]] = {}
        self._noticed: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def check(self, channel: str, user: str, direct: bool) -> Verdict:
        place = self.check_place(channel, direct)
        return place if place != Verdict.ALLOWED else self.check_person(user)

    def check_place(self, channel: str, direct: bool, fresh: bool = False) -> Verdict:
        """`fresh` asks Slack again instead of trusting the cache: a channel can be shared outside in the meantime."""
        if direct:
            return Verdict.ALLOWED if self._settings.allow_direct_messages else Verdict.DIRECT_DISABLED
        if not self._settings.allows_channel(channel):
            return Verdict.CHANNEL_NOT_ALLOWED
        info = self._channel(channel, fresh)
        if info is None:
            return Verdict.UNKNOWN
        shared_out = info.get("is_ext_shared") or info.get("is_pending_ext_shared") or (
            info.get("is_shared") and not info.get("is_org_shared"))
        return Verdict.CHANNEL_SHARED if shared_out else Verdict.ALLOWED

    def check_person(self, user: str) -> Verdict:
        member = self.member(user)
        if member is None:
            return Verdict.UNKNOWN
        if member.is_bot:
            return Verdict.BOT
        if member.is_guest:
            return Verdict.GUEST
        if self._team_id and member.team_id and member.team_id != self._team_id:
            return Verdict.EXTERNAL
        return Verdict.ALLOWED

    def name_of(self, user: str) -> str:
        member = self.member(user)
        return member.name if member else user

    def channel_name(self, channel: str) -> str:
        info = self._channel(channel)
        return str((info or {}).get("name") or channel)

    def member_channels(self) -> list[dict]:
        """The channels the bot was invited to, with id and name; empty when Slack does not answer."""
        channels: list[dict] = []
        cursor = None
        for _ in range(_MEMBER_PAGES):
            try:
                response = self._client.users_conversations(types="public_channel,private_channel",
                                                            exclude_archived=True, limit=200,
                                                            **({"cursor": cursor} if cursor else {}))
            except SlackApiError as exc:
                log.warning("channels not listed: %s", exc.response.get("error"))
                return channels
            channels.extend(response.get("channels") or [])
            cursor = (response.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return channels

    def first_notice(self, scope: str, subject: str) -> bool:
        """True once per (scope, subject) and process, so a refusal is said once and not on every mention."""
        with self._lock:
            if (scope, subject) in self._noticed:
                return False
            self._noticed.add((scope, subject))
            return True

    def member(self, user: str) -> Member | None:
        if not user:
            return None
        cached = self._cached(self._members, user)
        if cached is not False:
            return cached
        try:
            data = self._client.users_info(user=user)["user"]
        except SlackApiError as exc:
            log.warning("users.info %s failed: %s", user, exc.response.get("error"))
            data = None
        member = None
        if data:
            profile = data.get("profile") or {}
            member = Member(id=user,
                            name=profile.get("display_name") or profile.get("real_name") or data.get("real_name")
                            or data.get("name") or user,
                            team_id=str(data.get("team_id") or ""),
                            is_bot=bool(data.get("is_bot")) or user == "USLACKBOT",
                            is_guest=bool(data.get("is_restricted") or data.get("is_ultra_restricted")))
        with self._lock:
            self._members[user] = (self._clock(), member)
        return member

    def _channel(self, channel: str, fresh: bool = False) -> dict | None:
        cached = False if fresh else self._cached(self._channels, channel)
        if cached is not False:
            return cached
        try:
            info = self._client.conversations_info(channel=channel)["channel"]
        except SlackApiError as exc:
            log.warning("conversations.info %s failed: %s", channel, exc.response.get("error"))
            info = None
        with self._lock:
            self._channels[channel] = (self._clock(), info)
        return info

    def _cached(self, cache: dict, key: str):
        with self._lock:
            found = cache.get(key)
        if found and self._clock() - found[0] < _CACHE_S and found[1] is not None:
            return found[1]
        return False

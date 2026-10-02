"""Builds the bot from its parts and connects it to Slack over Socket Mode: the VPS needs no public URL."""
from __future__ import annotations

import logging
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from services.slack_bot.access import AccessPolicy
from services.slack_bot.answering import BotIdentity, ThreadAnswerer
from services.slack_bot.chat_client import ChatClient
from services.slack_bot.conversations import ConversationRegistry
from services.slack_bot.gateway import Gateway
from services.slack_bot.poster import SlackPoster
from services.slack_bot.recovery import Recovery
from services.slack_bot.scheduler import TurnScheduler
from services.slack_bot.settings import EVERY_CHANNEL, BotSettings
from services.slack_bot.state_store import STATE_RETENTION_S, StateStore

log = logging.getLogger(__name__)

_PRUNE_EVERY_S = 6 * 3600


def run(settings: BotSettings) -> None:
    app = App(token=settings.bot_token)
    auth = app.client.auth_test()
    identity = BotIdentity(user_id=str(auth["user_id"]), bot_id=str(auth.get("bot_id") or ""),
                           team_id=str(auth.get("team_id") or ""))
    poster = SlackPoster(app.client)
    store = StateStore(settings.state_path)
    registry = ConversationRegistry()
    access = AccessPolicy(app.client, settings, identity.team_id)
    answerer: ThreadAnswerer | None = None
    scheduler = TurnScheduler(settings.max_parallel_turns, handle=lambda key: answerer.handle(key))
    answerer = ThreadAnswerer(slack=app.client, poster=poster, registry=registry, scheduler=scheduler, store=store,
                              access=access, settings=settings, identity=identity,
                              chat=ChatClient(settings.chat_api_url, settings.chat_api_token))
    Gateway(poster=poster, access=access, registry=registry, scheduler=scheduler, store=store, settings=settings,
            identity=identity).register(app)
    Recovery(slack=app.client, poster=poster, answerer=answerer, registry=registry, scheduler=scheduler,
             store=store, settings=settings, identity=identity, access=access).run()
    scheduler.start()
    threading.Thread(target=_prune_forever, args=(store, registry), name="slack-prune", daemon=True).start()
    where = ("every internal channel it is in" if settings.every_channel
             else f"{len(settings.allowed_channels)} allowed channel(s)")
    log.info("Slack bot connected as %s; answers in %s, up to %d turn(s) at once",
             identity.user_id, where, settings.max_parallel_turns)
    _log_channels(access, settings)
    SocketModeHandler(app, settings.app_token).start()


def _log_channels(access: AccessPolicy, settings: BotSettings) -> None:
    """Where the bot is a member and whether it answers there: the ids SLACK_ALLOWED_CHANNELS takes."""
    channels = access.member_channels()
    if not channels:
        log.info("the bot is in no channel yet: invite it with /invite")
    for channel in channels:
        log.info("member of #%s (%s): %s", channel.get("name"), channel.get("id"),
                 "allowed" if settings.allows_channel(str(channel.get("id"))) else "not allowed")
    missing = settings.allowed_channels - {EVERY_CHANNEL} - {channel.get("id") for channel in channels}
    for channel_id in sorted(missing):
        log.warning("allowed channel %s does not have the bot: invite it there", channel_id)


def _prune_forever(store: StateStore, registry: ConversationRegistry) -> None:
    stop = threading.Event()
    while not stop.wait(_PRUNE_EVERY_S):
        try:
            store.prune()
            registry.forget_idle(STATE_RETENTION_S)
        except Exception:  # noqa: BLE001 — pruning is housekeeping, never worth the bot
            log.exception("state prune failed")

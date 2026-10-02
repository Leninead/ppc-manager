"""The gateway wired into a real Bolt app: Slack's payloads reach the right handler with the arguments it expects."""
import json
from urllib.parse import quote

from slack_bolt import App, BoltRequest
from slack_bolt.authorization import AuthorizeResult

from services.slack_bot.access import AccessPolicy
from services.slack_bot.conversations import ConversationRegistry
from services.slack_bot.gateway import Gateway
from services.slack_bot.poster import SlackPoster
from services.slack_bot.settings import BotSettings
from services.slack_bot.state_store import StateStore
from tests.slack_bot_fakes import BOT, FakeScheduler, FakeSlack


def authorize(enterprise_id, team_id, logger):
    # Bolt's default authorization calls auth.test on Slack: tests stay offline.
    return AuthorizeResult(enterprise_id=enterprise_id, team_id=team_id, bot_token="xoxb-test", bot_id=BOT.bot_id,
                           bot_user_id=BOT.user_id)


def wired(tmp_path):
    app = App(signing_secret="test", authorize=authorize, request_verification_enabled=False,
              process_before_response=True)
    slack = FakeSlack()
    settings = BotSettings(bot_token="x", app_token="y", allowed_channels=frozenset({"CPPC"}))
    scheduler = FakeScheduler()
    registry = ConversationRegistry()
    Gateway(poster=SlackPoster(slack, sleep=lambda s: None, interval_s=0),
            access=AccessPolicy(slack, settings, BOT.team_id), registry=registry, scheduler=scheduler,
            store=StateStore(tmp_path / "state.sqlite3"), settings=settings, identity=BOT).register(app)
    return app, slack, scheduler, registry


def event_request(event):
    body = {"type": "event_callback", "team_id": "T1", "api_app_id": "A1", "event": event,
            "event_id": f"Ev{event['ts']}", "event_time": 1}
    return BoltRequest(body=json.dumps(body), headers={"content-type": ["application/json"]})


def test_an_app_mention_reaches_the_gateway(tmp_path):
    app, slack, scheduler, _ = wired(tmp_path)
    response = app.dispatch(event_request({"type": "app_mention", "channel": "CPPC", "user": "U1",
                                           "ts": "1000.000", "text": "<@UBOT> ¿gasto?"}))
    assert response.status == 200
    assert scheduler.submitted == [(("CPPC", "1000.000"), 3.0)]
    assert slack.added("1000.000") == ["eyes"]


def test_a_direct_message_reaches_the_gateway(tmp_path):
    app, _, scheduler, registry = wired(tmp_path)
    app.dispatch(event_request({"type": "message", "channel_type": "im", "channel": "D1", "user": "U1",
                                "ts": "5.000", "text": "¿gasto?"}))
    assert scheduler.submitted == [(("D1", "5.000"), 3.0)]
    assert registry.snapshot(("D1", "5.000")).direct


def test_an_idea_click_is_acknowledged_and_asked(tmp_path):
    app, slack, scheduler, _ = wired(tmp_path)
    payload = {"type": "block_actions", "team": {"id": "T1"}, "user": {"id": "U2"}, "api_app_id": "A1",
               "channel": {"id": "CPPC"}, "container": {"type": "message", "channel_id": "CPPC"},
               "message": {"ts": "1000.500", "thread_ts": "1000.000"}, "trigger_id": "t",
               "actions": [{"action_id": "idea_1", "block_id": "b", "type": "button", "value": "¿Qué pauso?"}]}
    response = app.dispatch(BoltRequest(body=f"payload={quote(json.dumps(payload))}",
                                        headers={"content-type": ["application/x-www-form-urlencoded"]}))
    assert response.status == 200
    assert slack.posted[0]["metadata"]["event_payload"] == {"user": "U2", "question": "¿Qué pauso?"}
    assert scheduler.submitted == [(("CPPC", "1000.000"), 3.0)]

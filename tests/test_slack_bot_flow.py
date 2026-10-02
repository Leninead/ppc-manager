"""The Slack bot end to end against an in-memory Slack: the door, the thread's cycle and the recovery."""
import pytest

from ai import client as ai_client
from services.slack_bot import texts
from services.slack_bot.access import AccessPolicy, Verdict
from services.slack_bot.account_scope import ThreadScope
from services.slack_bot.answering import StatusLine, ThreadAnswerer
from services.slack_bot.conversations import ConversationRegistry, Stage
from services.slack_bot.gateway import Gateway
from services.slack_bot.poster import SlackPoster
from services.slack_bot.recovery import Recovery
from services.slack_bot.settings import BotSettings, ChannelAccount
from services.slack_bot.state_store import LAST_EVENT_TS, StateStore
from tests.slack_bot_fakes import BOT, FakeScheduler, FakeSlack, TurnScript, outcome, text_answer

CHANNEL = "CPPC"
ROOT = "1000.000"


class Scopes:
    def __init__(self, region="NA"):
        self.region = region

    def for_thread(self, channel, requested_by):
        scope = {"account_id": 1, "profile_id": "9", "requested_by": requested_by, "dynamic": True}
        return ThreadScope(scope if self.region else None, self.region, ChannelAccount("Love To Dream", "MX"))


class Bot:
    """Every part wired as bot.run wires it, around the fakes."""

    def __init__(self, tmp_path, turn=None, **settings):
        options = dict(bot_token="x", app_token="y", allowed_channels=frozenset({CHANNEL, "CSHARED"}),
                       gather_seconds=3.0, daily_questions_per_user=40, batch_max_questions=8)
        options.update(settings)
        self.settings = BotSettings(**options)
        self.slack = FakeSlack()
        self.poster = SlackPoster(self.slack, sleep=lambda s: None, interval_s=0)
        self.store = StateStore(tmp_path / "state.sqlite3")
        self.registry = ConversationRegistry()
        self.scheduler = FakeScheduler()
        self.access = AccessPolicy(self.slack, self.settings, BOT.team_id)
        self.turn = turn or TurnScript()
        self.recorded = []
        self.answerer = ThreadAnswerer(slack=self.slack, poster=self.poster, registry=self.registry,
                                       scheduler=self.scheduler, store=self.store, access=self.access, scopes=Scopes(),
                                       settings=self.settings, identity=BOT, run_turn=self.turn,
                                       directory=lambda: {"title": "Directorio", "content": "cuentas"},
                                       record=self.recorded.append, sleep=lambda s: None)
        self.gateway = Gateway(poster=self.poster, access=self.access, registry=self.registry,
                               scheduler=self.scheduler, store=self.store, settings=self.settings, identity=BOT)

    def mention(self, ts, user, text, thread_ts=ROOT, channel=CHANNEL):
        self.slack.add(channel, thread_ts, ts, user, f"<@UBOT> {text}")
        self.gateway.on_mention({"channel": channel, "user": user, "ts": ts, "text": f"<@UBOT> {text}",
                                 **({"thread_ts": thread_ts} if thread_ts != ts else {})})

    def say(self, ts, user, text, thread_ts=ROOT):
        self.slack.add(CHANNEL, thread_ts, ts, user, text)

    def answer(self, thread_ts=ROOT, channel=CHANNEL):
        self.answerer.handle((channel, thread_ts))

    def recovery(self, **extra):
        return Recovery(slack=self.slack, poster=self.poster, answerer=self.answerer, registry=self.registry,
                        scheduler=self.scheduler, store=self.store, settings=self.settings, identity=BOT,
                        access=self.access, **extra)


# --- The door ---

def test_a_mention_is_marked_queued_after_the_gathering_window(tmp_path):
    bot = Bot(tmp_path)
    bot.mention(ROOT, "U1", "¿cuánto gastó SB?")
    assert bot.slack.added(ROOT) == ["eyes"]
    assert bot.scheduler.submitted == [((CHANNEL, ROOT), 3.0)]
    assert bot.store.find(CHANNEL, ROOT).owes_answers
    assert bot.store.questions_last_day("U1") == 1


def test_more_mentions_while_queued_do_not_queue_the_thread_twice(tmp_path):
    bot = Bot(tmp_path)
    bot.mention(ROOT, "U1", "uno")
    bot.mention("1000.100", "U2", "dos")
    assert len(bot.scheduler.submitted) == 1


def test_slack_retrying_an_event_counts_once(tmp_path):
    bot = Bot(tmp_path)
    event = {"channel": CHANNEL, "user": "U1", "ts": ROOT, "text": "<@UBOT> hola che, ¿gasto?"}
    bot.gateway.on_mention(event)
    bot.gateway.on_mention(event)
    assert bot.store.questions_last_day("U1") == 1


def test_a_channel_not_allowed_hears_it_once(tmp_path):
    bot = Bot(tmp_path)
    bot.mention("1.1", "U1", "¿gasto?", thread_ts="1.1", channel="COTHER")
    bot.mention("1.2", "U1", "¿gasto?", thread_ts="1.2", channel="COTHER")
    assert bot.slack.texts() == [texts.CHANNEL_NOT_ALLOWED]
    assert bot.scheduler.submitted == []


def test_a_channel_shared_with_another_organization_is_refused_even_if_allowed(tmp_path):
    bot = Bot(tmp_path)
    bot.mention("1.1", "U1", "¿gasto?", thread_ts="1.1", channel="CSHARED")
    assert bot.slack.texts() == [texts.CHANNEL_SHARED]


@pytest.mark.parametrize("user", ["UGUEST", "UEXT"])
def test_guests_and_people_from_other_workspaces_are_told_privately_once(tmp_path, user):
    bot = Bot(tmp_path)
    bot.mention("1.1", user, "dame todo", thread_ts="1.1")
    bot.mention("1.2", user, "dame todo", thread_ts="1.2")
    assert [e["text"] for e in bot.slack.ephemerals] == [texts.NOT_A_MEMBER]
    assert bot.scheduler.submitted == []


def test_a_bare_mention_gets_ideas_and_no_turn(tmp_path):
    bot = Bot(tmp_path)
    bot.mention(ROOT, "U1", "ayuda")
    [post] = bot.slack.posted
    assert post["blocks"][1]["type"] == "actions"
    assert len(post["blocks"][1]["elements"]) == 3
    assert bot.scheduler.submitted == []


def test_over_the_daily_limit_the_mention_is_refused_and_kept_out_of_the_batch(tmp_path):
    bot = Bot(tmp_path, daily_questions_per_user=1)
    bot.mention(ROOT, "U1", "primera")
    bot.mention("1000.100", "U1", "segunda")
    bot.mention("1000.200", "U1", "tercera")
    assert bot.slack.added("1000.100") == ["no_entry"]
    assert [e["text"] for e in bot.slack.ephemerals] == [texts.limit_reached(1)]
    assert bot.registry.snapshot((CHANNEL, ROOT)).excluded == {"1000.100", "1000.200"}


def test_a_busy_bot_says_how_many_threads_are_ahead(tmp_path):
    bot = Bot(tmp_path)
    bot.scheduler.waiting = (1, 2)
    bot.mention(ROOT, "U1", "¿gasto?")
    assert bot.slack.texts() == [
        "Estoy respondiendo en 2 conversaciones y hay 1 conversación esperando antes que esta; las respondo en orden."]


def test_mentions_in_a_burst_hear_their_place_in_line_even_before_any_turn_starts(tmp_path):
    from services.slack_bot.scheduler import TurnScheduler

    bot = Bot(tmp_path, allowed_channels=frozenset({"C1", "C2", "C3"}))
    bot.gateway._scheduler = TurnScheduler(2, handle=lambda key: None)
    for index, channel in enumerate(("C1", "C2", "C3")):
        bot.mention(f"10{index}.0", "U1", "¿gasto?", thread_ts=f"10{index}.0", channel=channel)
    assert bot.slack.texts() == ["Hay 2 conversaciones esperando antes que esta; las respondo en orden."]
    assert bot.slack.posted[0]["channel"] == "C3"


def test_direct_messages_need_no_mention_and_ignore_edits_and_bots(tmp_path):
    bot = Bot(tmp_path)
    bot.gateway.on_message({"channel_type": "im", "channel": "D1", "user": "U1", "ts": "5.0", "text": "¿gasto?"})
    bot.gateway.on_message({"channel_type": "im", "channel": "D1", "user": "U1", "ts": "5.1",
                            "subtype": "message_changed"})
    bot.gateway.on_message({"channel_type": "im", "channel": "D1", "bot_id": "B9", "ts": "5.2", "text": "x"})
    bot.gateway.on_message({"channel_type": "channel", "channel": CHANNEL, "user": "U1", "ts": "5.3", "text": "x"})
    assert bot.scheduler.submitted == [(("D1", "5.0"), 3.0)]
    assert bot.registry.snapshot(("D1", "5.0")).direct


def test_an_idea_click_becomes_a_question_in_the_clickers_name(tmp_path):
    bot = Bot(tmp_path)
    bot.gateway.on_idea(lambda: None, {"user": {"id": "U2"}, "channel": {"id": CHANNEL},
                                       "message": {"ts": "1000.500", "thread_ts": ROOT},
                                       "actions": [{"value": "¿Qué keywords me están quemando plata?"}]})
    [echo] = bot.slack.posted
    assert echo["metadata"]["event_payload"] == {"user": "U2", "question": "¿Qué keywords me están quemando plata?"}
    assert bot.slack.added(echo["ts"]) == ["eyes"]
    assert bot.scheduler.submitted == [((CHANNEL, ROOT), 3.0)]


def test_slacks_assistant_pane_opens_with_the_apps_ideas(tmp_path):
    bot = Bot(tmp_path)
    bot.gateway.on_assistant_thread_started({"assistant_thread": {"channel_id": "D1", "thread_ts": "7.0"}})
    [prompts] = bot.slack.prompts
    assert len(prompts["prompts"]) == 3
    assert all(prompt["title"] and prompt["message"] for prompt in prompts["prompts"])


# --- The thread's cycle ---

def test_questions_and_conversation_go_in_one_turn_and_come_back_one_message_each(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1"], "SB gastó **$120**."), text_answer(["q2"], "Subió 12%.")))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "¿cuánto gastó SB?")
    bot.say("1000.100", "U2", "creo que subió por SB")
    bot.mention("1000.200", "U3", "¿y contra la anterior?")
    bot.answer()

    [call] = turn.calls
    assert call["question_ids"] == ["q1", "q2"]
    assert call["prompt"].splitlines()[-3:] == ["q1 · Lenin: ¿cuánto gastó SB?", "Marcos: creo que subió por SB",
                                                "q2 · Ana: ¿y contra la anterior?"]
    assert call["session_id"] is None
    assert [d["title"] for d in call["documents"]] == ["Directorio"]
    assert "#ppc-ltd" in call["note"] and "Love To Dream (MX)" in call["note"] and "región NA" in call["note"]
    assert call["ads_scope"]["requested_by"] == "slack:Lenin, Ana"

    first, second = bot.slack.posted
    assert first["blocks"][0]["elements"][0]["text"] == "Para <@U1> · «¿cuánto gastó SB?»"
    assert first["blocks"][1]["elements"][0]["text"] == "Leyó: Serie diaria · Agency OS"
    assert first["text"].startswith("<@U1> SB gastó")
    assert second["blocks"][0]["elements"][0]["text"] == "Para <@U3> · «¿y contra la anterior?»"
    assert second["blocks"][-1] == {"type": "context", "elements": [
        {"type": "mrkdwn", "text": texts.keep_going(False)}]}
    assert bot.slack.added(ROOT) == ["eyes", "white_check_mark"]
    assert bot.slack.added("1000.200") == ["eyes", "white_check_mark"]

    stored = bot.store.find(CHANNEL, ROOT)
    assert (stored.watermark, stored.session_id, stored.region, stored.owes_answers) == ("1000.200", "S1", "NA", False)
    assert bot.registry.snapshot((CHANNEL, ROOT)).stage == Stage.IDLE
    [row] = bot.recorded
    assert row.page == "slack" and row.cost_usd == 0.42 and row.question == ("Lenin: ¿cuánto gastó SB?\n"
                                                                             "Ana: ¿y contra la anterior?")


def test_the_status_line_names_what_the_turn_reads_and_clears_at_the_end(tmp_path, monkeypatch):
    monkeypatch.setattr(StatusLine, "min_gap_s", 0)
    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q1"], "ok"))))
    bot.mention(ROOT, "U1", "¿gasto?")
    bot.answer()
    statuses = [status["status"] for status in bot.slack.statuses]
    assert statuses == [texts.THINKING, "está leyendo: Campañas · Amazon Ads", ""]


def test_the_next_cycle_resumes_the_session_and_reads_only_what_is_new(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1"], "uno")), outcome(text_answer(["q1"], "dos"), session_id="S1"))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "primera")
    bot.answer()
    bot.mention("1000.900", "U2", "segunda")
    bot.answer()
    assert turn.calls[1]["session_id"] == "S1"
    assert turn.calls[1]["documents"] == []
    assert turn.calls[1]["prompt"].splitlines()[-1] == "q1 · Marcos: segunda"
    assert bot.slack.posted[-1]["blocks"][-1]["type"] != "context" or \
        bot.slack.posted[-1]["blocks"][-1]["elements"][0]["text"] != texts.keep_going(False)


def test_a_session_that_cannot_be_resumed_is_opened_again_with_the_thread_so_far(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1"], "uno")), ai_client.UpstreamError("session not found"),
                      outcome(text_answer(["q1"], "dos"), session_id="S2"))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "primera")
    bot.answer()
    bot.mention("1000.900", "U2", "segunda")
    bot.answer()
    resumed, reopened = turn.calls[1:]
    assert resumed["session_id"] == "S1"
    assert reopened["session_id"] is None
    assert [d["title"] for d in reopened["documents"]] == ["Directorio", "Conversación previa de este hilo de Slack"]
    assert "Lenin: primera" in reopened["documents"][1]["content"]
    assert bot.store.find(CHANNEL, ROOT).session_id == "S2"


def test_one_answer_for_two_people_who_asked_the_same_mentions_both(tmp_path):
    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q1", "q2"], "Lo mismo para los dos."))))
    bot.mention(ROOT, "U1", "¿gasto de LTD?")
    bot.mention("1000.100", "U2", "¿cuánto gasta LTD?")
    bot.answer()
    [post] = bot.slack.posted
    assert post["blocks"][0]["elements"][0]["text"].startswith("Para <@U1> y <@U2>")
    assert post["text"].startswith("<@U1> <@U2>")


def test_a_skipped_mention_gets_an_ok_hand_and_no_answer(tmp_path):
    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q2"], "ACoS 30%."), skipped={"q1": "saludo"})))
    bot.mention(ROOT, "U1", "che qué capo")
    bot.mention("1000.100", "U2", "¿ACoS?")
    bot.answer()
    assert bot.slack.added(ROOT) == ["eyes", "ok_hand"]
    assert len(bot.slack.posted) == 1


def test_a_question_left_unanswered_is_asked_once_more_and_then_reported(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1"], "uno"), missing=("q2",)),
                      outcome(missing=("q1",)))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "primera")
    bot.mention("1000.100", "U2", "la difícil")
    bot.answer()
    assert bot.scheduler.submitted[-1] == ((CHANNEL, ROOT), 0.0)
    assert bot.store.find(CHANNEL, ROOT).carried == {"1000.100": 1}

    bot.answer()
    assert turn.calls[1]["prompt"].splitlines()[-1] == "q1 · Marcos: la difícil"
    assert bot.slack.texts()[-1] == texts.not_answered("la difícil")
    assert bot.slack.added("1000.100") == ["eyes", "x"]
    assert bot.store.find(CHANNEL, ROOT).carried == {}


def test_questions_past_the_cap_come_in_the_next_turn(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1", "q2"], "dos")), outcome(text_answer(["q1"], "la tercera")))
    bot = Bot(tmp_path, turn=turn, batch_max_questions=2)
    for index, ts in enumerate([ROOT, "1000.100", "1000.200"]):
        bot.mention(ts, "U1", f"pregunta {index}")
    bot.answer()
    assert texts.more_than_fit(1) in bot.slack.texts()
    assert bot.scheduler.submitted[-1] == ((CHANNEL, ROOT), 0.0)
    bot.answer()
    assert turn.calls[1]["prompt"].splitlines()[-1] == "q1 · Lenin: pregunta 2"


def test_a_quota_hit_says_when_it_retries_and_gives_up_after_two_failures(tmp_path):
    turn = TurnScript(*(ai_client.QuotaExceeded("cuota", 300) for _ in range(3)))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "¿gasto?")
    bot.answer()
    assert bot.slack.texts()[-1] == texts.quota_retry(300)
    assert bot.scheduler.submitted[-1] == ((CHANNEL, ROOT), 300)
    bot.answer()
    bot.answer()
    assert bot.slack.texts()[-1] == texts.gave_up("cuota")
    assert bot.slack.added(ROOT) == ["eyes", "x"]
    assert bot.store.find(CHANNEL, ROOT).watermark == ROOT
    assert bot.recorded[-1].error == "cuota" and bot.recorded[-1].answer is None


def test_a_provider_failure_retries_with_the_same_questions(tmp_path):
    turn = TurnScript(ai_client.ProviderDown("caído"), outcome(text_answer(["q1"], "ok")))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "¿gasto?")
    bot.answer()
    assert bot.slack.texts()[-1] == texts.failure_retry("caído", 30)
    bot.answer()
    assert turn.calls[1]["question_ids"] == ["q1"]
    assert bot.slack.added(ROOT) == ["eyes", "white_check_mark"]


def test_charts_and_tables_arrive_in_order(tmp_path):
    from services.slack_bot.batch_reply import BatchAnswer

    blocks = [{"kind": "text", "text": "Así se reparte:"},
              {"kind": "pie", "metric": "Gasto", "items": [{"label": "A", "value": 3, "display": "$3"},
                                                           {"label": "B", "value": 1, "display": "$1"}]},
              {"kind": "table", "columns": ["Campaña", "ACoS"], "rows": [[{"value": "A", "tone": "neutral"},
                                                                         {"value": "30%", "tone": "good"}]]}]
    bot = Bot(tmp_path, turn=TurnScript(outcome(BatchAnswer(("q1",), blocks))))
    bot.mention(ROOT, "U1", "¿cómo se reparte?")
    bot.answer()
    assert [upload["title"] for upload in bot.slack.uploads] == ["Gasto"]
    assert [block["type"] for block in bot.slack.posted[-1]["blocks"]] == ["table", "context"]


def test_a_message_slack_refuses_is_sent_again_as_plain_text(tmp_path):
    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q1"], "Respuesta"))))
    bot.mention(ROOT, "U1", "¿gasto?")
    bot.slack.refuse_posts_with = "invalid_blocks"
    bot.answer()
    [post] = bot.slack.posted
    assert post["text"].startswith("<@U1> Respuesta")
    assert post["blocks"][0]["type"] == "section"


def test_a_thread_whose_questions_were_deleted_goes_idle(tmp_path):
    bot = Bot(tmp_path)
    bot.mention(ROOT, "U1", "¿gasto?")
    bot.slack.threads[(CHANNEL, ROOT)].clear()
    bot.answer()
    assert bot.turn.calls == []
    assert bot.registry.snapshot((CHANNEL, ROOT)).stage == Stage.IDLE


# --- Recovery ---

def test_after_a_restart_threads_that_owed_answers_are_queued_again(tmp_path):
    bot = Bot(tmp_path)
    bot.mention(ROOT, "U1", "¿gasto?")
    fresh = Bot(tmp_path)
    queued = fresh.recovery().run()
    assert queued == 1
    assert fresh.scheduler.submitted == [((CHANNEL, ROOT), 0.0)]


def test_mentions_sent_while_the_bot_was_away_are_found_and_read_from_there(tmp_path):
    bot = Bot(tmp_path)
    bot.store.set_meta(LAST_EVENT_TS, "1999999990.0")
    bot.slack.history[CHANNEL] = [
        {"ts": "1999999995.0", "user": "U1", "text": "<@UBOT> ¿gasto de hoy?"},
        {"ts": "1999999993.0", "user": "U2", "text": "hilo viejo", "latest_reply": "1999999996.0"},
        {"ts": "1999999994.0", "user": "U3", "text": "sin mención"}]
    bot.slack.add(CHANNEL, "1999999993.0", "1999999993.0", "U2", "hilo viejo")
    bot.slack.add(CHANNEL, "1999999993.0", "1999999996.0", "U3", "<@UBOT> ¿y esto?")
    recovery = bot.recovery(clock=lambda: 2_000_000_000.0)
    assert recovery.run() == 2
    assert {key for key, _ in bot.scheduler.submitted} == {(CHANNEL, "1999999995.0"), (CHANNEL, "1999999993.0")}
    assert bot.registry.snapshot((CHANNEL, "1999999993.0")).watermark == "1999999990.0"


def test_a_first_start_does_not_scan_channels(tmp_path):
    bot = Bot(tmp_path)
    bot.slack.history[CHANNEL] = [{"ts": "1.0", "user": "U1", "text": "<@UBOT> vieja"}]
    recovery = bot.recovery()
    assert recovery.run() == 0


# --- Access ---

def test_access_verdicts(tmp_path):
    bot = Bot(tmp_path, allow_direct_messages=False)
    check = bot.access.check
    assert check(CHANNEL, "U1", False) == Verdict.ALLOWED
    assert check("COTHER", "U1", False) == Verdict.CHANNEL_NOT_ALLOWED
    assert check("CSHARED", "U1", False) == Verdict.CHANNEL_SHARED
    assert check(CHANNEL, "UGUEST", False) == Verdict.GUEST
    assert check(CHANNEL, "UEXT", False) == Verdict.EXTERNAL
    assert check(CHANNEL, "UNOBODY", False) == Verdict.UNKNOWN
    assert check("D1", "U1", True) == Verdict.DIRECT_DISABLED


# --- Separate channels never share a conversation ---

def test_two_channels_are_answered_in_separate_turns_and_sessions(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1"], "Respuesta de cuentas"), session_id="S-cuentas"),
                      outcome(text_answer(["q1"], "Respuesta de general"), session_id="S-general"),
                      outcome(text_answer(["q1"], "Seguimiento de cuentas"), session_id="S-cuentas"))
    bot = Bot(tmp_path, turn=turn, allowed_channels=frozenset({"CCUENTAS", "CGENERAL"}))
    bot.mention("1.0", "U1", "¿cómo viene LTD?", thread_ts="1.0", channel="CCUENTAS")
    bot.mention("2.0", "U2", "¿qué es el TACoS?", thread_ts="2.0", channel="CGENERAL")
    bot.answer(thread_ts="1.0", channel="CCUENTAS")
    bot.answer(thread_ts="2.0", channel="CGENERAL")
    bot.mention("1.5", "U1", "¿y la semana pasada?", thread_ts="1.0", channel="CCUENTAS")
    bot.answer(thread_ts="1.0", channel="CCUENTAS")

    cuentas, general, follow_up = turn.calls
    assert "LTD" in cuentas["prompt"] and "TACoS" not in cuentas["prompt"]
    assert "TACoS" in general["prompt"] and "LTD" not in general["prompt"]
    assert (cuentas["session_id"], general["session_id"]) == (None, None)
    assert follow_up["session_id"] == "S-cuentas"
    assert "TACoS" not in follow_up["prompt"]
    assert {post["channel"]: post["text"].split(" ", 1)[1] for post in bot.slack.posted[:2]} == {
        "CCUENTAS": "Respuesta de cuentas", "CGENERAL": "Respuesta de general"}


# --- Fixes from the code review ---

def test_a_mention_inside_a_direct_message_is_a_direct_question(tmp_path):
    bot = Bot(tmp_path, allowed_channels=frozenset())
    bot.gateway.on_mention({"channel": "D1", "channel_type": "im", "user": "U1", "ts": "5.0", "text": "<@UBOT> ¿x?"})
    bot.gateway.on_message({"channel": "D1", "channel_type": "im", "user": "U1", "ts": "5.0", "text": "<@UBOT> ¿x?"})
    assert bot.slack.texts() == []
    assert bot.scheduler.submitted == [(("D1", "5.0"), 3.0)]
    assert bot.registry.snapshot(("D1", "5.0")).direct


def test_answers_survive_a_crash_between_the_turn_and_slack_and_the_model_is_not_asked_again(tmp_path, monkeypatch):
    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q1"], "La respuesta"))))
    bot.mention(ROOT, "U1", "¿gasto?")

    real = bot.answerer.deliver_pending
    calls = []

    def crash_after_the_turn(key):
        calls.append(key)
        if len(calls) == 1:  # the cycle's own check for leftovers, before the turn
            return real(key)
        raise SystemExit("killed right after the turn was stored")

    monkeypatch.setattr(bot.answerer, "deliver_pending", crash_after_the_turn)
    with pytest.raises(SystemExit):
        bot.answer()
    assert bot.slack.posted == []
    assert bot.store.find(CHANNEL, ROOT).watermark == ROOT

    restarted = Bot(tmp_path)
    restarted.slack.threads = bot.slack.threads
    restarted.recovery().run()
    assert restarted.scheduler.submitted == [((CHANNEL, ROOT), 0.0)]
    restarted.answer()
    assert restarted.turn.calls == []
    assert restarted.slack.posted[0]["text"].startswith("<@U1> La respuesta")
    assert restarted.slack.added(ROOT) == ["white_check_mark"]
    assert restarted.store.pending_delivery((CHANNEL, ROOT)) is None


def test_a_delivery_interrupted_halfway_resumes_where_it_stopped(tmp_path):
    turn = TurnScript(outcome(text_answer(["q1"], "uno"), text_answer(["q2"], "dos")))
    bot = Bot(tmp_path, turn=turn)
    bot.mention(ROOT, "U1", "primera")
    bot.mention("1000.100", "U2", "segunda")
    original = bot.poster.post_part
    calls = []

    def flaky(channel, thread_ts, part):
        calls.append(part)
        if len(calls) == 2:
            raise ConnectionError("network down")
        original(channel, thread_ts, part)

    bot.poster.post_part = flaky
    bot.answer()
    assert len(bot.slack.posted) == 1
    assert bot.scheduler.submitted[-1] == ((CHANNEL, ROOT), 30)
    bot.answer()
    assert [post["text"].split()[1] for post in bot.slack.posted] == ["uno", "dos"]
    assert len(turn.calls) == 1


def test_a_delivery_step_that_always_fails_is_dropped_after_three_attempts(tmp_path):
    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q1"], "uno"))))
    bot.mention(ROOT, "U1", "¿gasto?")

    def broken(channel, thread_ts, part):
        raise ConnectionError("down")

    bot.poster.post_part = broken
    for _ in range(3):
        bot.answer()
    assert bot.store.pending_delivery((CHANNEL, ROOT)) is None


def test_a_channel_shared_outside_after_the_mention_gets_no_answer(tmp_path, monkeypatch):
    from tests import slack_bot_fakes

    bot = Bot(tmp_path)
    bot.mention(ROOT, "U1", "¿gasto?")
    monkeypatch.setitem(slack_bot_fakes.CHANNELS, CHANNEL, {"name": "ppc-ltd", "is_ext_shared": True})
    bot.answer()
    assert bot.turn.calls == []
    assert bot.slack.texts() == [texts.CHANNEL_SHARED]
    assert bot.registry.snapshot((CHANNEL, ROOT)).stage == Stage.IDLE
    assert bot.store.find(CHANNEL, ROOT).watermark == ROOT


def test_a_chart_slack_refuses_still_arrives_as_text(tmp_path):
    from slack_sdk.errors import SlackApiError

    from services.slack_bot.batch_reply import BatchAnswer

    blocks = [{"kind": "bars", "metric": "Gasto", "items": [{"label": "A", "value": 2, "display": "$2",
                                                              "tone": "neutral"}]}]
    bot = Bot(tmp_path, turn=TurnScript(outcome(BatchAnswer(("q1",), blocks))))
    bot.mention(ROOT, "U1", "¿gasto?")

    def refuse(**kwargs):
        raise SlackApiError("refused", {"ok": False, "error": "file_uploads_disabled"})

    bot.slack.files_upload_v2 = refuse
    bot.answer()
    assert any(post["text"] == "Gasto\nGasto\nA: $2" for post in bot.slack.posted)


def test_a_carried_question_whose_author_left_is_marked_failed(tmp_path, monkeypatch):
    from tests import slack_bot_fakes

    bot = Bot(tmp_path, turn=TurnScript(outcome(text_answer(["q1"], "uno"), missing=("q2",))))
    bot.mention(ROOT, "U1", "primera")
    bot.mention("1000.100", "U2", "segunda")
    bot.answer()
    monkeypatch.setitem(slack_bot_fakes.MEMBERS, "U2", {**slack_bot_fakes.MEMBERS["U2"], "team_id": "TGONE"})
    bot.access._members.clear()
    bot.answer()
    assert bot.slack.added("1000.100") == ["eyes", "x"]
    assert bot.store.find(CHANNEL, ROOT).carried == {}


def test_a_rate_limit_without_a_number_waits_a_second_instead_of_crashing():
    from slack_sdk.errors import SlackApiError

    class Limited(dict):
        headers = {"Retry-After": "soon"}

    waits = []
    poster = SlackPoster(FakeSlack(), sleep=waits.append, interval_s=0)
    attempts = []

    def method(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise SlackApiError("limited", Limited(ok=False, error="ratelimited"))
        return {"ok": True}

    assert poster.call(method) == {"ok": True}
    assert waits == [1.0]


def test_with_every_channel_allowed_any_internal_channel_answers_but_a_shared_one_does_not(tmp_path):
    bot = Bot(tmp_path, allowed_channels=frozenset({"*"}))
    assert bot.access.check("COTHER", "U1", False) == Verdict.ALLOWED
    assert bot.access.check("CSHARED", "U1", False) == Verdict.CHANNEL_SHARED


def test_with_every_channel_allowed_recovery_reads_the_channels_the_bot_is_in(tmp_path):
    bot = Bot(tmp_path, allowed_channels=frozenset({"*"}))
    bot.store.set_meta(LAST_EVENT_TS, "1999999990.0")
    bot.slack.member_of = [{"id": "COTHER", "name": "random"}]
    bot.slack.history["COTHER"] = [{"ts": "1999999995.0", "user": "U1", "text": "<@UBOT> ¿gasto?"}]
    assert bot.recovery(clock=lambda: 2_000_000_000.0).run() == 1
    assert bot.scheduler.submitted == [(("COTHER", "1999999995.0"), 0.0)]

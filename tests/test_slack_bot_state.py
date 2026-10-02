"""The Slack bot's moving parts: thread stages, the turn scheduler, what survives a restart, and its settings."""
import threading
import time

import pytest

from core.chat.ads_scope import AccountVehicle
from services.slack_bot import __main__ as entry
from services.slack_bot.account_scope import AccountScopes
from services.slack_bot.conversations import SESSION_MAX_AGE_S, Conversation, ConversationRegistry, Stage
from services.slack_bot.scheduler import TurnScheduler
from services.slack_bot.settings import BotSettings, ChannelAccount
from services.slack_bot.state_store import StateStore

KEY = ("C1", "1.0")


# --- Thread stages ---

def test_the_first_mention_queues_and_the_rest_wait_for_the_running_turn():
    registry = ConversationRegistry()
    assert registry.mention(*KEY, direct=False) is True
    assert registry.mention(*KEY, direct=False) is False
    registry.start(KEY)
    assert registry.mention(*KEY, direct=False) is False
    assert registry.finish(KEY, watermark="1.5") is True
    assert registry.snapshot(KEY).stage == Stage.QUEUED


def test_a_turn_with_nothing_pending_leaves_the_thread_idle():
    registry = ConversationRegistry()
    registry.mention(*KEY, direct=False)
    registry.start(KEY)
    assert registry.finish(KEY, watermark="1.5", session_id="S1", region="NA", new_session=True) is False
    snapshot = registry.snapshot(KEY)
    assert (snapshot.stage, snapshot.watermark, snapshot.session_id, snapshot.region) == (Stage.IDLE, "1.5", "S1", "NA")


def test_exclusions_older_than_the_watermark_are_forgotten():
    registry = ConversationRegistry()
    registry.mention(*KEY, direct=False)
    registry.exclude(KEY, "1.2", direct=False)
    registry.exclude(KEY, "1.9", direct=False)
    registry.start(KEY)
    registry.finish(KEY, watermark="1.5")
    assert registry.snapshot(KEY).excluded == {"1.9"}


def test_failures_count_until_a_turn_succeeds():
    registry = ConversationRegistry()
    registry.mention(*KEY, direct=False)
    registry.start(KEY)
    registry.finish(KEY, failed=True)
    registry.start(KEY)
    registry.finish(KEY, failed=True)
    assert registry.snapshot(KEY).failures == 2
    registry.start(KEY)
    registry.finish(KEY, watermark="2.0")
    assert registry.snapshot(KEY).failures == 0


def test_idle_threads_nobody_wrote_in_are_forgotten_and_busy_ones_kept():
    now = [1000.0]
    registry = ConversationRegistry(clock=lambda: now[0])
    registry.mention("C1", "old", direct=False)
    registry.start(("C1", "old"))
    registry.finish(("C1", "old"), watermark="1.0")
    registry.mention("C1", "waiting", direct=False)
    now[0] += 9 * 24 * 3600
    assert registry.forget_idle(8 * 24 * 3600) == 1
    assert registry.snapshot(("C1", "old")) is None
    assert registry.snapshot(("C1", "waiting")) is not None


@pytest.mark.parametrize("change, resumed", [
    ({}, "S1"),
    ({"region": "EU"}, None),
    ({"age": SESSION_MAX_AGE_S + 1}, None),
])
def test_a_session_is_resumed_only_in_its_region_and_before_the_provider_deletes_it(change, resumed):
    conversation = Conversation(*KEY, session_id="S1", session_started_at=1000.0, region="NA")
    now = 1000.0 + change.get("age", 60)
    assert conversation.session_to_resume(change.get("region", "NA"), now) == resumed


# --- Scheduler ---

def test_no_more_turns_run_at_once_than_workers_and_every_thread_is_served():
    running, peak, done = [0], [0], []
    lock = threading.Lock()

    def handle(key):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
            done.append(key)

    scheduler = TurnScheduler(2, handle)
    for index in range(6):
        scheduler.submit(("C", str(index)))
    scheduler.start()
    deadline = time.monotonic() + 5
    while len(done) < 6 and time.monotonic() < deadline:
        time.sleep(0.01)
    scheduler.stop()
    assert sorted(done) == [("C", str(i)) for i in range(6)]
    assert peak[0] == 2


def test_threads_are_served_in_arrival_order_and_a_delay_is_respected():
    served = []
    scheduler = TurnScheduler(1, served.append)
    scheduler.submit(("C", "late"), delay=0.3)
    scheduler.submit(("C", "first"))
    scheduler.submit(("C", "second"))
    assert scheduler.ahead_of(("C", "second")) == 2
    scheduler.start()
    deadline = time.monotonic() + 3
    while len(served) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    scheduler.stop()
    assert served == [("C", "first"), ("C", "second"), ("C", "late")]


def test_submitting_a_waiting_thread_again_keeps_its_place():
    scheduler = TurnScheduler(1, lambda key: None)
    scheduler.submit(("C", "a"))
    scheduler.submit(("C", "b"))
    scheduler.submit(("C", "a"), delay=10)
    assert scheduler.ahead_of(("C", "a")) == 0
    assert scheduler.ahead_of(("C", "b")) == 1


def test_a_failing_turn_does_not_kill_the_worker():
    served = []

    def handle(key):
        served.append(key)
        if key == ("C", "boom"):
            raise RuntimeError("boom")

    scheduler = TurnScheduler(1, handle)
    scheduler.submit(("C", "boom"))
    scheduler.submit(("C", "next"))
    scheduler.start()
    deadline = time.monotonic() + 3
    while len(served) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    scheduler.stop()
    assert served == [("C", "boom"), ("C", "next")]


# --- What survives a restart ---

def test_a_conversation_comes_back_as_it_was_saved(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    saved = Conversation(*KEY, direct=True, session_id="S1", session_started_at=5.0, region="NA", watermark="1.5",
                         carried={"1.2": 1}, excluded={"1.3"}, owes_answers=True, updated_at=10.0)
    store.save(saved)
    store.save(saved)
    assert StateStore(tmp_path / "state.sqlite3").find(*KEY) == saved


def test_questions_count_over_the_last_24_hours(tmp_path):
    now = [100_000.0]
    store = StateStore(tmp_path / "state.sqlite3", clock=lambda: now[0])
    store.record_question("U1")
    now[0] += 3600
    store.record_question("U1")
    assert store.questions_last_day("U1") == 2
    now[0] += 23 * 3600 + 1
    assert store.questions_last_day("U1") == 1


def test_old_conversations_are_pruned(tmp_path):
    now = [10_000_000.0]
    store = StateStore(tmp_path / "state.sqlite3", clock=lambda: now[0])
    store.save(Conversation("C1", "1.0", updated_at=now[0] - 9 * 24 * 3600))
    store.save(Conversation("C1", "2.0", updated_at=now[0]))
    store.prune()
    assert [c.thread_ts for c in store.recent(0)] == ["2.0"]


# --- Settings and the account of each channel ---

def test_settings_read_the_environment_and_ignore_broken_values():
    settings = BotSettings.from_env({
        "SLACK_BOT_TOKEN": "xoxb", "SLACK_APP_TOKEN": "xapp", "SLACK_ALLOWED_CHANNELS": "C1, C2,",
        "SLACK_CHANNEL_ACCOUNTS": '{"C1": {"client": "Love To Dream", "country": "mx"}, "C2": {"client": ""}}',
        "SLACK_MAX_PARALLEL_TURNS": "3", "SLACK_BATCH_MAX_QUESTIONS": "cero", "SLACK_GATHER_SECONDS": "-1",
        "SLACK_ALLOW_DIRECT_MESSAGES": "no", "SLACK_EFFORT": "medium"})
    assert settings.configured
    assert settings.allowed_channels == {"C1", "C2"}
    assert settings.channel_accounts == {"C1": ChannelAccount("Love To Dream", "MX")}
    assert (settings.max_parallel_turns, settings.batch_max_questions, settings.gather_seconds) == (3, 8, 3.0)
    assert settings.allow_direct_messages is False
    assert settings.effort == "medium"


def test_without_tokens_the_bot_is_not_configured():
    assert not BotSettings.from_env({}).configured


def test_without_tokens_the_entry_point_idles_instead_of_crashing(monkeypatch):
    for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    class Idled(Exception):
        pass

    def sleep(seconds):
        raise Idled

    monkeypatch.setattr(entry.time, "sleep", sleep)
    monkeypatch.setattr(entry, "quiet_streamlit", lambda: None)
    with pytest.raises(Idled):
        entry.main()


def vehicle(region, country):
    return AccountVehicle(account_id=1 if region == "NA" else 2, profile_id="9", region=region, country_code=country,
                          client="X")


def test_a_channels_country_picks_the_live_amazon_ads_region():
    settings = BotSettings(channel_accounts={"CDE": ChannelAccount("Cliente DE", "DE")})
    scopes = AccountScopes(settings, load_vehicles=lambda: [vehicle("NA", "US"), vehicle("NA", "MX"),
                                                            vehicle("EU", "DE")])
    eu = scopes.for_thread("CDE", "slack:Lenin")
    assert (eu.region, eu.ads_scope["account_id"], eu.ads_scope["requested_by"]) == ("EU", 2, "slack:Lenin")
    assert scopes.for_thread("COTRO", "slack:Lenin").region == "NA"


def test_without_connected_accounts_the_turn_goes_without_live_amazon_ads():
    scope = AccountScopes(BotSettings(), load_vehicles=lambda: []).for_thread("C1", "slack:Lenin")
    assert (scope.ads_scope, scope.region) == (None, None)


def test_a_dm_thread_first_seen_through_a_refused_mention_stays_direct():
    registry = ConversationRegistry()
    registry.exclude(("D1", "5.0"), "5.0", direct=True)
    registry.mention("D1", "5.0", direct=True)
    assert registry.snapshot(("D1", "5.0")).direct


def test_a_closed_thread_waits_idle_for_a_new_mention():
    registry = ConversationRegistry()
    registry.mention(*KEY, direct=False)
    registry.start(KEY)
    registry.mention(*KEY, direct=False)
    registry.close(KEY, "9.0")
    snapshot = registry.snapshot(KEY)
    assert (snapshot.stage, snapshot.owes_answers, snapshot.watermark) == (Stage.IDLE, False, "9.0")
    assert registry.mention(*KEY, direct=False) is True


def test_a_turns_answers_are_stored_with_its_watermark_and_survive_until_posted(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    store.save(Conversation(*KEY, watermark="2.0", updated_at=1.0), delivery={"answers": ["a"]})
    reopened = StateStore(tmp_path / "state.sqlite3")
    assert reopened.find(*KEY).watermark == "2.0"
    assert reopened.pending_delivery(KEY) == ({"answers": ["a"]}, 0, 0)
    reopened.delivery_step_done(KEY, 2)
    assert reopened.delivery_failed(KEY) == 1
    assert reopened.pending_delivery(KEY) == ({"answers": ["a"]}, 2, 1)
    assert reopened.pending_delivery_keys() == [KEY]
    reopened.drop_delivery(KEY)
    assert reopened.pending_delivery(KEY) is None


def test_a_star_allows_every_channel_and_ids_allow_only_themselves():
    every = BotSettings.from_env({"SLACK_ALLOWED_CHANNELS": "*"})
    assert every.every_channel and every.allows_channel("CANY")
    listed = BotSettings.from_env({"SLACK_ALLOWED_CHANNELS": "C1"})
    assert not listed.every_channel
    assert listed.allows_channel("C1") and not listed.allows_channel("C2")

"""amazon_ads worker CLI: config errors, one-line tick summary, stoppable loop, backfill command. No network."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.amazon_ads import worker
from core.amazon_ads.ingestion_job import TickSummary
from core.integrations import crypto
from core.integrations.worker import WorkerError

NOW = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)


class _FakeIngestion:
    def __init__(self, summaries=None, crash_first: bool = False):
        self._summaries = list(summaries or [])
        self._crash_first = crash_first
        self.ticked_at: list[datetime] = []
        self.stop_checks = []

    def run_tick(self, now_utc: datetime, stop_requested=lambda: False) -> TickSummary:
        self.ticked_at.append(now_utc)
        self.stop_checks.append(stop_requested)
        if self._crash_first and len(self.ticked_at) == 1:
            raise RuntimeError("unexpected tick failure")
        return self._summaries.pop(0) if self._summaries else TickSummary()


class _StoppingSleep:
    """Stops the loop after a number of sleep calls instead of waiting for real."""

    def __init__(self, stop: worker.StopFlag, stop_after_calls: int):
        self._stop = stop
        self._stop_after_calls = stop_after_calls
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if len(self.calls) >= self._stop_after_calls:
            self._stop.request()


class _FakeRest:
    def __init__(self, profile_rows, enqueue_answers, holder_rows=(), open_job_rows=None):
        self._profile_rows = profile_rows
        self._enqueue_answers = list(enqueue_answers)
        self._holder_rows = list(holder_rows)
        self._open_job_rows = open_job_rows
        self.inserted: list[dict] = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [dict(row) for row in self._profile_rows]
        if self._open_job_rows is not None and "status" in params:
            return list(self._open_job_rows)
        return list(self._holder_rows)

    def insert_ignore(self, table, row, on_conflict, *, timeout_s=8):
        self.inserted.append(row)
        return self._enqueue_answers.pop(0)


@pytest.fixture
def unconfigured_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("INTEGRATIONS_WORKER_JWT", raising=False)


def test_tick_without_database_configuration_exits_with_code_two(unconfigured_env, capsys):
    assert worker.main(["tick"]) == worker.CONFIG_ERROR_EXIT == 2
    assert "INTEGRATIONS_WORKER_JWT" in capsys.readouterr().err


def test_backfill_without_database_configuration_exits_with_code_two(unconfigured_env):
    assert worker.main(["backfill", "--profile-id", "1001"]) == 2


def test_tick_without_the_sealing_key_exits_with_code_two(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SUPABASE_URL", "http://rest-gateway.invalid")
    monkeypatch.setenv("INTEGRATIONS_WORKER_JWT", "test-jwt")
    monkeypatch.delenv(crypto.PRIVATE_KEY_ENV, raising=False)
    monkeypatch.setenv(crypto.PRIVATE_KEY_FILE_ENV, str(tmp_path / "missing.pem"))

    assert worker.main(["tick"]) == 2
    assert "no private key" in capsys.readouterr().err


def test_tick_prints_exactly_one_summary_line(capsys):
    summary = TickSummary(profiles_active=19, jobs_planned=2, reports_created=5, rows_written=1234,
                          errors=["poll_reports: AdsApiError: HTTP 500", "job 7: ReportFailed: boom"])
    ingestion = _FakeIngestion([summary])

    assert worker.command_tick(build=lambda: ingestion, clock=lambda: NOW) == 0

    output = capsys.readouterr().out
    assert output.count("\n") == 1
    assert "19 active profiles" in output and "1234 rows" in output and "2 errors" in output
    assert "first error: poll_reports: AdsApiError: HTTP 500" in output
    assert ingestion.ticked_at == [NOW]


def test_run_loop_stops_on_the_stop_flag_without_real_sleeping():
    stop = worker.StopFlag()
    sleep = _StoppingSleep(stop, stop_after_calls=4)
    ingestion = _FakeIngestion()

    exit_code = worker.command_run(stop, build=lambda: ingestion, clock=lambda: NOW, sleep=sleep, tick_seconds=3)

    assert exit_code == 0
    assert len(ingestion.ticked_at) == 2
    assert sleep.calls == [1.0, 1.0, 1.0, 1.0]


def test_run_loop_survives_a_crashing_tick(caplog):
    stop = worker.StopFlag()
    ingestion = _FakeIngestion(crash_first=True)

    with caplog.at_level(logging.ERROR):
        worker.command_run(stop, build=lambda: ingestion, clock=lambda: NOW,
                           sleep=_StoppingSleep(stop, stop_after_calls=2), tick_seconds=1)

    assert len(ingestion.ticked_at) == 2
    assert "tick crashed" in caplog.text


def test_run_without_configuration_logs_once_and_idles_until_stopped(caplog):
    stop = worker.StopFlag()
    build_attempts = []

    def unconfigured_build():
        build_attempts.append(1)
        raise WorkerError("missing SUPABASE_URL or INTEGRATIONS_WORKER_JWT")

    with caplog.at_level(logging.ERROR):
        exit_code = worker.command_run(stop, build=unconfigured_build, sleep=_StoppingSleep(stop, stop_after_calls=6),
                                       tick_seconds=2)

    assert exit_code == 2
    assert len(build_attempts) == 3
    assert caplog.text.count("not configured") == 1


def test_run_starts_ticking_once_the_key_shows_up():
    stop = worker.StopFlag()
    ingestion = _FakeIngestion()
    outcomes = [crypto.SealError("no private key yet"), ingestion]

    def build():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    worker.command_run(stop, build=build, clock=lambda: NOW, sleep=_StoppingSleep(stop, stop_after_calls=2),
                       tick_seconds=1)

    assert ingestion.ticked_at == [NOW]


def test_stop_flag_is_raised_by_the_signal_handler_signature():
    stop = worker.StopFlag()
    stop.request(15, None)
    assert stop.requested is True


def test_backfill_command_queues_once_and_reports_the_job_holding_the_key(capsys):
    profile_row = {"profile_id": "1001", "status": "active", "region": "NA", "country_code": "US",
                   "timezone": "America/Los_Angeles", "connection_id": 5, "account_id": 9}
    rest = _FakeRest([profile_row], enqueue_answers=[True, False], holder_rows=[{"id": 31, "status": "running"}])

    assert worker.command_backfill("1001", rest_factory=lambda: rest, clock=lambda: NOW) == 0
    assert worker.command_backfill("1001", rest_factory=lambda: rest, clock=lambda: NOW) == 1

    first, second = capsys.readouterr().out.strip().splitlines()
    assert first == "queued backfill for 1001: 2026-07-11..2026-09-13"
    assert second == "not queued: job 31 (running) already holds the backfill of 1001"
    assert rest.inserted[0]["dedupe_key"] == "amazon_ads:1001:backfill:2026-09-14"
    assert rest.inserted[0]["trigger"] == "backfill"


def test_backfill_command_refuses_while_a_backfill_from_an_earlier_day_is_still_open(capsys):
    profile_row = {"profile_id": "1001", "status": "active", "region": "NA", "timezone": "America/Los_Angeles"}
    open_jobs = [{"id": 12, "status": "retrying", "trigger": "scheduled_daily", "window_start": "2026-08-31",
                  "window_end": "2026-09-13"},
                 {"id": 31, "status": "running", "trigger": "retry", "window_start": "2026-07-10",
                  "window_end": "2026-09-12"}]
    rest = _FakeRest([profile_row], enqueue_answers=[True], open_job_rows=open_jobs)

    assert worker.command_backfill("1001", rest_factory=lambda: rest, clock=lambda: NOW) == 1

    assert capsys.readouterr().out.strip() == "not queued: job 31 (running) already holds the backfill of 1001"
    assert rest.inserted == []


def test_run_loop_lets_the_tick_see_a_stop_requested_while_it_runs():
    stop = worker.StopFlag()
    ingestion = _FakeIngestion()

    worker.command_run(stop, build=lambda: ingestion, clock=lambda: NOW, sleep=_StoppingSleep(stop, stop_after_calls=1),
                       tick_seconds=1)

    assert len(ingestion.stop_checks) == 1
    assert ingestion.stop_checks[0]() is True


def test_compose_gives_the_ads_worker_two_minutes_to_stop_and_rotates_its_log():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.db.yml").read_text(encoding="utf-8")
    service = compose.split("\n  ads-sync-worker:\n", 1)[1].split("\n\n", 1)[0]

    assert "\n    stop_grace_period: 2m\n" in service
    log_rotation = '\n    logging:\n      driver: json-file\n      options:\n        max-size: "10m"\n        max-file: "5"\n'
    assert log_rotation in service


def test_backfill_command_refuses_unknown_or_inactive_profiles():
    unknown = _FakeRest([], enqueue_answers=[])
    reauth = _FakeRest([{"profile_id": "1001", "status": "needs_reauth"}], enqueue_answers=[])

    assert worker.command_backfill("1001", rest_factory=lambda: unknown, clock=lambda: NOW) == 1
    assert worker.command_backfill("1001", rest_factory=lambda: reauth, clock=lambda: NOW) == 1
    assert unknown.inserted == [] and reauth.inserted == []


@pytest.mark.parametrize("raw, expected", [("", 60), ("15", 15.0), ("abc", 60), ("-5", 60)])
def test_tick_interval_comes_from_the_environment(monkeypatch, raw, expected):
    monkeypatch.setenv(worker.TICK_SECONDS_ENV, raw)
    assert worker._tick_seconds_from_env() == expected

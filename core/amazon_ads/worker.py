"""Always-on Amazon Ads search term sync (the `ads-sync-worker` service).

    python -m core.amazon_ads.worker run                          tick every ADS_TICK_SECONDS until SIGTERM
    python -m core.amazon_ads.worker tick                         one tick, one summary line
    python -m core.amazon_ads.worker backfill --profile-id <id>   queue a backfill now (dedupe-safe)
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone

import requests

from core.amazon_ads.ingestion_job import PROFILE_SYNC_TABLE, IngestionJob, TickSummary
from core.amazon_ads.raw_reports import raw_root
from core.amazon_ads.sync_planner import PROFILE_ACTIVE, SEARCH_TERMS_KIND, ProfileState, backfill_job, is_backfill
from core.amazon_ads.tokens import TokenManager
from core.integrations import crypto
from core.integrations.amazon_identity import SLUG
from core.integrations.store import _Rest
from core.integrations.sync_jobs import JOBS_TABLE, OPEN_STATUSES, SyncJobStore, _in_filter, parse_date
from core.integrations.worker import WorkerError, _rest_worker

log = logging.getLogger("amazon_ads.worker")

TICK_SECONDS_ENV = "ADS_TICK_SECONDS"
DEFAULT_TICK_SECONDS = 60
CONFIG_ERROR_EXIT = 2
STOP_CHECK_SECONDS = 1.0
_CONFIG_ERRORS = (WorkerError, crypto.SealError)


class StopFlag:
    """Set by SIGTERM or SIGINT; the loop checks it between ticks and while it sleeps."""

    def __init__(self):
        self.requested = False

    def request(self, signum: int | None = None, frame=None) -> None:
        self.requested = True


def build_ingestion_job() -> IngestionJob:
    """Raises WorkerError or SealError when the database JWT or the sealing key is missing."""
    rest = _rest_worker()
    private_pem = crypto.read_existing_private_key()
    return IngestionJob(
        rest=rest,
        jobs=SyncJobStore(rest),
        tokens=TokenManager(rest, private_pem),
        raw_dir=raw_root(),
        holder=f"amazon_ads-{socket.gethostname()}-{os.getpid()}",
    )


def command_tick(build: Callable[[], IngestionJob] = build_ingestion_job,
                 clock: Callable[[], datetime] | None = None) -> int:
    try:
        ingestion = build()
    except _CONFIG_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    print(format_summary(ingestion.run_tick((clock or _utc_now)())))
    return 0


def command_run(stop: StopFlag, *, build: Callable[[], IngestionJob] = build_ingestion_job,
                clock: Callable[[], datetime] | None = None, sleep: Callable[[float], None] = time.sleep,
                tick_seconds: float | None = None) -> int:
    interval = tick_seconds if tick_seconds is not None else _tick_seconds_from_env()
    ingestion = _wait_for_configuration(stop, build, sleep, interval)
    if ingestion is None:
        return CONFIG_ERROR_EXIT
    log.info("amazon_ads worker running, one tick every %s s", interval)
    while not stop.requested:
        try:
            summary = ingestion.run_tick((clock or _utc_now)(), stop_requested=lambda: stop.requested)
        except Exception:
            # The loop is the service: a tick that blows up must not take the container down with it.
            log.exception("amazon_ads: tick crashed")
        else:
            if not summary.is_idle:
                log.info("%s", format_summary(summary))
        _sleep_until_stopped(interval, stop, sleep)
    log.info("amazon_ads worker stopped")
    return 0


def command_backfill(profile_id: str, *, rest_factory: Callable[[], _Rest] = _rest_worker,
                     clock: Callable[[], datetime] | None = None) -> int:
    try:
        rest = rest_factory()
    except WorkerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CONFIG_ERROR_EXIT
    try:
        return _queue_backfill(rest, profile_id, (clock or _utc_now)())
    except requests.RequestException as exc:
        print(f"error: the database did not answer: {exc}", file=sys.stderr)
        return 1


def _queue_backfill(rest: _Rest, profile_id: str, now_utc: datetime) -> int:
    rows = rest.select(PROFILE_SYNC_TABLE, {"select": "*", "profile_id": f"eq.{profile_id}", "limit": "1"})
    if not rows:
        print(f"error: profile {profile_id} is not in {PROFILE_SYNC_TABLE}; run a tick first", file=sys.stderr)
        return 1
    state = ProfileState.from_row(rows[0])
    if state.status != PROFILE_ACTIVE:
        print(f"error: profile {profile_id} is {state.status}, not active", file=sys.stderr)
        return 1
    new_job = backfill_job(state, now_utc)
    # The key only covers today: a backfill started on an earlier local day may still be running.
    holders = _open_backfills(rest, profile_id)
    if not holders:
        if SyncJobStore(rest).enqueue(new_job):
            print(f"queued backfill for {profile_id}: {new_job.window_start}..{new_job.window_end}")
            return 0
        holders = rest.select(JOBS_TABLE, {"select": "id,status", "dedupe_key": f"eq.{new_job.dedupe_key}",
                                           "limit": "1"})
    holder = f"job {holders[0]['id']} ({holders[0]['status']})" if holders else "another job"
    print(f"not queued: {holder} already holds the backfill of {profile_id}")
    return 1


def _open_backfills(rest: _Rest, profile_id: str) -> list[dict]:
    open_jobs = rest.select(JOBS_TABLE, {
        "select": "id,status,trigger,window_start,window_end",
        "integration_slug": f"eq.{SLUG}",
        "job_kind": f"eq.{SEARCH_TERMS_KIND}",
        "external_account_id": f"eq.{profile_id}",
        "status": _in_filter(OPEN_STATUSES),
    })
    return [
        job for job in open_jobs
        if is_backfill(job.get("trigger") or "", parse_date(job.get("window_start")), parse_date(job.get("window_end")))
    ]


def format_summary(summary: TickSummary) -> str:
    line = (
        f"tick · {summary.profiles_active} active profiles · {summary.jobs_planned} planned · "
        f"{summary.reports_created} created · {summary.reports_polled} polled · {summary.reports_saved} saved · "
        f"{summary.rows_written} rows · {summary.jobs_completed} completed · {summary.jobs_failed} failed · "
        f"{summary.raw_pruned} pruned · {len(summary.errors)} errors"
    )
    return f"{line} · first error: {summary.errors[0]}" if summary.errors else line


def _wait_for_configuration(stop: StopFlag, build: Callable[[], IngestionJob], sleep: Callable[[float], None],
                            interval: float) -> IngestionJob | None:
    """Idles instead of exiting, so a host without the JWT or the key yet does not crash-loop the container."""
    last_reported = ""
    while not stop.requested:
        try:
            return build()
        except _CONFIG_ERRORS as exc:
            if str(exc) != last_reported:
                log.error("amazon_ads worker is not configured, waiting: %s", exc)
                last_reported = str(exc)
        _sleep_until_stopped(interval, stop, sleep)
    return None


def _sleep_until_stopped(seconds: float, stop: StopFlag, sleep: Callable[[float], None]) -> None:
    remaining = seconds
    while remaining > 0 and not stop.requested:
        step = min(STOP_CHECK_SECONDS, remaining)
        sleep(step)
        remaining -= step


def _tick_seconds_from_env() -> float:
    raw = os.environ.get(TICK_SECONDS_ENV, "").strip()
    if not raw:
        return DEFAULT_TICK_SECONDS
    try:
        seconds = float(raw)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        log.warning("amazon_ads: %s=%r is not a positive number, using %s s", TICK_SECONDS_ENV, raw,
                    DEFAULT_TICK_SECONDS)
        return DEFAULT_TICK_SECONDS
    return seconds


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="amazon_ads.worker")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="tick until SIGTERM")
    commands.add_parser("tick", help="run one tick and print its summary")
    backfill = commands.add_parser("backfill", help="queue a backfill for one profile")
    backfill.add_argument("--profile-id", required=True)
    args = parser.parse_args(argv)

    if args.command == "tick":
        return command_tick()
    if args.command == "backfill":
        return command_backfill(args.profile_id)
    stop = StopFlag()
    signal.signal(signal.SIGTERM, stop.request)
    signal.signal(signal.SIGINT, stop.request)
    return command_run(stop)


if __name__ == "__main__":
    raise SystemExit(main())

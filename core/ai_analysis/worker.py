"""Always-on AI analysis worker (the `ads-ai-worker` service).

    python -m core.ai_analysis.worker run                        plan and run analyses every AI_TICK_SECONDS
    python -m core.ai_analysis.worker tick [--profile-id <id>]   plan once and run what is due, then exit

Planning and the heartbeat run on the main thread every tick; provider calls take minutes, so each job runs on
its own thread and the loop keeps beating.
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
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone

import requests

from core.ai_analysis.store import AiAnalysisStore
from core.ai_analysis.str_analysis_job import PlanSummary, StrAnalysisJob
from core.amazon_ads.report_provider import ReportProvider
from core.integrations.store import _Rest
from core.integrations.sync_jobs import JOBS_TABLE, SyncJobStore

log = logging.getLogger("ai_analysis.worker")

WORKER_NAME = "ai_analysis"
JWT_ENV = "AI_WORKER_JWT"
TICK_SECONDS_ENV = "AI_TICK_SECONDS"
CONCURRENCY_ENV = "AI_ANALYSIS_CONCURRENCY"
DEFAULT_TICK_SECONDS = 60
DEFAULT_CONCURRENCY = 2
# Covers the report read before the call; the job extends it past the provider timeout once the call starts.
LEASE_SECONDS = 1800
HEARTBEATS_TABLE = "integration_worker_heartbeats"
IMAGE_TAG_ENV = "IMAGE_TAG"
CONFIG_ERROR_EXIT = 2
STOP_CHECK_SECONDS = 1.0


class ConfigurationError(RuntimeError):
    pass


class StopFlag:
    def __init__(self):
        self.requested = False

    def request(self, signum: int | None = None, frame=None) -> None:
        self.requested = True


def worker_rest() -> _Rest:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get(JWT_ENV, "").strip()
    if not (url and key):
        raise ConfigurationError(f"missing SUPABASE_URL or {JWT_ENV}")
    return _Rest(url, key)


def build_job(rest: _Rest) -> StrAnalysisJob:
    return StrAnalysisJob(store=AiAnalysisStore(rest), jobs=SyncJobStore(rest), reports=ReportProvider(rest),
                          clock=_utc_now)


class AnalysisWorker:
    def __init__(self, *, rest_factory: Callable[[], _Rest], concurrency: int,
                 profile_ids: frozenset[str] | None = None, clock: Callable[[], datetime] = None):
        self._rest_factory = rest_factory
        self._rest = rest_factory()
        self._planner = build_job(self._rest)
        self._store = AiAnalysisStore(self._rest)
        self._pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="ai-analysis")
        self._concurrency = concurrency
        self._running: dict[int, Future] = {}
        self._profile_ids = profile_ids
        self._clock = clock or _utc_now
        self._holder = f"{WORKER_NAME}-{socket.gethostname()}-{os.getpid()}"

    def tick(self) -> dict:
        plan = PlanSummary()
        try:
            plan = self._planner.plan(self._profile_ids)
        except Exception as exc:
            log.exception("ai analysis: planning crashed")
            plan.errors.append(f"plan: {exc}")
        claimed = self._claim()
        summary = {**asdict(plan), "jobs_claimed": claimed, "jobs_running": len(self._running)}
        self._write_heartbeat(summary)
        return summary

    def wait_for_running(self) -> None:
        for future in list(self._running.values()):
            future.result()
        self._running.clear()

    def release_running(self) -> None:
        """Hands in-flight jobs back to the queue on shutdown, so a restart retries them without spending an attempt."""
        job_ids = list(self._running)
        if not job_ids:
            return
        now = self._clock().isoformat()
        for job_id in job_ids:
            try:
                self._rest.update(JOBS_TABLE, {"id": f"eq.{job_id}", "status": "eq.running"}, {
                    "status": "pending", "phase": "", "lease_holder": "", "lease_expires_at": None,
                    "next_attempt_at": now,
                })
            except requests.RequestException as exc:
                log.warning("ai analysis: job %s could not be released on shutdown: %s", job_id, exc)
        log.info("ai analysis: released %d running jobs on shutdown", len(job_ids))

    def _claim(self) -> int:
        self._running = {job_id: future for job_id, future in self._running.items() if not future.done()}
        free = self._concurrency - len(self._running)
        if free <= 0:
            return 0
        jobs = self._store.claim_due(self._holder, free, LEASE_SECONDS)
        for job in jobs:
            self._running[job.id] = self._pool.submit(self._execute, job)
        return len(jobs)

    def _execute(self, job) -> None:
        # One client per thread: provider calls outlive many ticks and must not share a session.
        outcome = build_job(self._rest_factory()).execute(job)
        log.info("ai analysis job %s finished (analysis %s%s)", outcome.job_id, outcome.analysis_id,
                 ", reused" if outcome.reused else "")

    def _write_heartbeat(self, summary: dict) -> None:
        try:
            self._rest.upsert(HEARTBEATS_TABLE, {
                "worker_name": WORKER_NAME,
                "last_tick_at": self._clock().isoformat(),
                "image_tag": os.environ.get(IMAGE_TAG_ENV, ""),
                "summary": {**summary, "errors": summary.get("errors", [])[:5]},
            }, on_conflict="worker_name")
        except requests.RequestException as exc:
            log.warning("ai analysis: heartbeat not written: %s", exc)


def command_run(stop: StopFlag, *, worker_factory: Callable[[], AnalysisWorker],
                sleep: Callable[[float], None] = time.sleep, tick_seconds: float | None = None) -> int:
    interval = tick_seconds if tick_seconds is not None else _seconds_from_env(TICK_SECONDS_ENV, DEFAULT_TICK_SECONDS)
    worker = _wait_for_configuration(stop, worker_factory, sleep, interval)
    if worker is None:
        return CONFIG_ERROR_EXIT
    log.info("ai analysis worker running, one tick every %s s", interval)
    while not stop.requested:
        try:
            summary = worker.tick()
        except Exception:
            log.exception("ai analysis: tick crashed")
        else:
            if summary["analyses_queued"] or summary["jobs_claimed"] or summary["errors"]:
                log.info("tick · %s", summary)
        _sleep_until_stopped(interval, stop, sleep)
    worker.release_running()
    log.info("ai analysis worker stopped")
    return 0


def command_tick(worker: AnalysisWorker) -> int:
    summary = worker.tick()
    worker.wait_for_running()
    print(f"tick · {summary}")
    return 0


def _wait_for_configuration(stop: StopFlag, factory: Callable[[], AnalysisWorker], sleep, interval: float):
    last_reported = ""
    while not stop.requested:
        try:
            return factory()
        except ConfigurationError as exc:
            if str(exc) != last_reported:
                log.error("ai analysis worker is not configured, waiting: %s", exc)
                last_reported = str(exc)
        _sleep_until_stopped(interval, stop, sleep)
    return None


def _sleep_until_stopped(seconds: float, stop: StopFlag, sleep: Callable[[float], None]) -> None:
    remaining = seconds
    while remaining > 0 and not stop.requested:
        step = min(STOP_CHECK_SECONDS, remaining)
        sleep(step)
        remaining -= step


def _seconds_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = 0
    if value <= 0:
        log.warning("ai analysis: %s=%r is not a positive number, using %s", name, raw, default)
        return default
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="ai_analysis.worker")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="plan and run analyses until SIGTERM")
    tick = commands.add_parser("tick", help="plan once, run what is due and exit")
    tick.add_argument("--profile-id", action="append", default=[],
                      help="only plan these profiles (repeatable); claimed jobs run regardless")
    args = parser.parse_args(argv)
    concurrency = int(_seconds_from_env(CONCURRENCY_ENV, DEFAULT_CONCURRENCY))

    if args.command == "tick":
        try:
            worker = AnalysisWorker(rest_factory=worker_rest, concurrency=concurrency,
                                    profile_ids=frozenset(args.profile_id) or None)
        except ConfigurationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return CONFIG_ERROR_EXIT
        return command_tick(worker)
    stop = StopFlag()
    signal.signal(signal.SIGTERM, stop.request)
    signal.signal(signal.SIGINT, stop.request)
    return command_run(stop, worker_factory=lambda: AnalysisWorker(rest_factory=worker_rest,
                                                                   concurrency=concurrency))


if __name__ == "__main__":
    raise SystemExit(main())

"""Stored STR analyses: the store, planning when API data arrives, running a job and the worker loop."""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from ai import client
from core.ai_analysis.store import AiAnalysisStore, NewAnalysis, StoredAnalysis
from core.ai_analysis.str_analysis_job import (
    BACKGROUND_TIMEOUT_SECONDS,
    DATA_CHANGED_ERROR,
    FAILED_BEFORE_NOTE,
    JOB_KIND,
    PROVIDER_RESPONSE_MARGIN_SECONDS,
    REUSED_WARNING,
    SUPERSEDED_WARNING,
    StrAnalysisJob,
)
from core.ai_analysis.worker import WORKER_NAME, AnalysisWorker
from core.amazon_ads.report_provider import ProfileOption
from core.integrations.store import StoreError
from core.integrations.sync_jobs import SyncJob, SyncJobStore
from core.search_term_analysis import StrAnalysisParams
from core.search_term_frame import SOURCE_API, SearchTermSource, add_ratios

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
SEARCH_ROWS = [
    {"Customer Search Term": "cheap toy box", "Campaign Name": "LK - Broad", "Ad Group Name": "AG",
     "Impressions": 900, "Clicks": 40, "Spend": 25.0, "7 Day Total Sales": 0.0, "7 Day Total Orders (#)": 0},
    {"Customer Search Term": "luna pajamas", "Campaign Name": "LK - Exact", "Ad Group Name": "AG",
     "Impressions": 800, "Clicks": 30, "Spend": 10.0, "7 Day Total Sales": 150.0, "7 Day Total Orders (#)": 6},
]
RESULT = {"negativos": [], "harvest": [], "campanas": [],
          "synthesis": {"situation": "s", "week_actions": [], "mid_term": [], "risks": []}}


class FakeRest:
    """In-memory PostgREST over the tables the analysis worker reads and writes."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {"ai_analyses": [], "ai_analysis_settings": [],
                                              "integration_sync_jobs": [], "integration_worker_heartbeats": []}
        self.rpc_calls = []
        self.claimable: list[dict] = []
        self._next_id = 100

    @staticmethod
    def _matches(row, params):
        for column, condition in params.items():
            if column in ("select", "order", "limit", "on_conflict"):
                continue
            value = (row.get("params") or {}).get("input_digest") if column == "params->>input_digest" \
                else row.get(column)
            operator, _, expected = condition.partition(".")
            if operator == "eq" and str(value) != expected:
                return False
            if operator == "neq" and str(value) == expected:
                return False
            if operator == "in" and str(value) not in expected.strip("()").split(","):
                return False
        return True

    def select(self, table, params):
        rows = [dict(row) for row in self.tables[table] if self._matches(row, params)]
        return rows[:int(params["limit"])] if "limit" in params else rows

    def insert_returning(self, table, row, **_):
        self._next_id += 1
        stored = {**row, "id": self._next_id}
        self.tables[table].append(stored)
        return stored

    def insert_ignore(self, table, row, on_conflict, **_):
        if any(existing.get(on_conflict) == row.get(on_conflict) for existing in self.tables[table]):
            return False
        self.insert_returning(table, {"status": "pending", "attempts": 0, **row})
        return True

    def update(self, table, params, changes, stamp=True):
        for row in self.tables[table]:
            if self._matches(row, params):
                row.update(changes)

    def upsert(self, table, row, on_conflict=None):
        self.tables[table] = [existing for existing in self.tables[table]
                              if existing.get(on_conflict) != row.get(on_conflict)] + [dict(row)]

    def rpc(self, name, args, **_):
        self.rpc_calls.append((name, args))
        if name == "claim_ai_jobs":
            claimed, self.claimable = self.claimable[:args["p_limit"]], self.claimable[args["p_limit"]:]
            return claimed
        raise AssertionError(f"unexpected rpc {name}")


class FakeReports:
    def __init__(self, profiles, rows=SEARCH_ROWS):
        self._profiles = profiles
        self.rows = rows
        self.reads = []

    def profiles(self):
        return list(self._profiles)

    def search_terms(self, option, start, end):
        self.reads.append((option.profile_id, start, end))
        frame = pd.DataFrame(self.rows, columns=list(SEARCH_ROWS[0]))
        return SearchTermSource(frame=add_ratios(frame, 7), source=SOURCE_API,
                                currency_code=option.currency_code, label=option.label, signature="sig",
                                attribution_days=7, bulk_ready=True, profile_id=option.profile_id,
                                window_start=start, window_end=end)


def _profile(**overrides):
    row = {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids US",
           "country_code": "US", "currency_code": "USD", "account_type": "seller",
           "timezone": "America/Los_Angeles", "status": "active", "data_from": "2026-07-11",
           "data_through": "2026-09-14", "refreshed_on": "2026-09-15",
           "last_success_at": "2026-09-15T10:00:00+00:00", "last_error": ""}
    row.update(overrides)
    return ProfileOption.from_row(row)


_JOB_PARAMS = {"target_acos": 30, "price": 30.0, "harvest_target_acos": 30, "harvest_price": 30.0,
               "harvest_min_clicks": 15, "brand_terms": []}


def _digest_of(params, rows=SEARCH_ROWS):
    """The fingerprint the page sends with a request for these rows, computed the way the worker computes it."""
    runner = _runner(FakeRest(), FakeReports([_profile()], rows))
    _, call = runner._prepare(_profile(), StrAnalysisParams.from_dict(params, "USD"), date(2026, 8, 16),
                              date(2026, 9, 14), "es")
    return call.input_digest


def _job(fake, **overrides):
    row = {"id": 9, "integration_slug": "amazon_ads", "job_kind": JOB_KIND, "trigger": "manual",
           "external_account_id": "111", "status": "running", "attempts": 0, "max_attempts": 3,
           "window_start": "2026-08-16", "window_end": "2026-09-14", "requested_by": "ana",
           "deadline_at": (NOW + timedelta(hours=6)).isoformat(),
           "params": {"lang": "es", "input_digest": _digest_of(_JOB_PARAMS), "params": dict(_JOB_PARAMS)}}
    row.update(overrides)
    fake.tables["integration_sync_jobs"].append(row)
    return SyncJob.from_row(row)


def _runner(fake, reports, ask=None):
    return StrAnalysisJob(store=AiAnalysisStore(fake), jobs=SyncJobStore(fake), reports=reports,
                          ask=ask or (lambda **call: {"structured_output": RESULT, "session_id": "sess",
                                                      "request_id": "req", "usage": {"output_tokens": 900},
                                                      "cost_estimate_usd": 0.41}),
                          clock=lambda: NOW)


# ── planning ──────────────────────────────────────────────────────────────────

def test_new_data_queues_one_analysis_of_the_canonical_window():
    fake, reports = FakeRest(), FakeReports([_profile()])

    summary = _runner(fake, reports).plan()

    (job,) = fake.tables["integration_sync_jobs"]
    assert summary.analyses_queued == 1
    assert (job["job_kind"], job["trigger"], job["window_start"], job["window_end"]) == (
        JOB_KIND, "scheduled_daily", "2026-09-08", "2026-09-14")
    assert job["params"]["lang"] == "es" and job["dedupe_key"].endswith(job["params"]["input_digest"])


def test_data_that_already_has_an_analysis_costs_nothing():
    fake, reports = FakeRest(), FakeReports([_profile()])
    runner = _runner(fake, reports)
    runner.plan()
    digest = fake.tables["integration_sync_jobs"][0]["params"]["input_digest"]
    fake.tables["integration_sync_jobs"].clear()
    fake.tables["ai_analyses"].append({"id": 1, "module": "str", "subject_id": "111", "input_digest": digest,
                                       "status": "done"})

    newer_sync = _runner(fake, FakeReports([_profile(last_success_at="2026-09-15T11:00:00+00:00")])).plan()

    assert (newer_sync.analyses_queued, newer_sync.already_covered) == (0, 1)
    assert fake.tables["integration_sync_jobs"] == []


def test_an_unchanged_account_is_not_read_again_until_its_data_or_parameters_change():
    fake, reports = FakeRest(), FakeReports([_profile()])
    runner = _runner(fake, reports)
    runner.plan()
    runner.plan()
    assert len(reports.reads) == 1

    fake.tables["ai_analysis_settings"].append({"module": "str", "subject_id": "111", "updated_by": "ana",
                                                "updated_at": "2026-09-15T11:30:00+00:00",
                                                "params": {"target_acos": 45, "price": 30.0,
                                                           "harvest_price": 30.0}})
    runner.plan()
    assert len(reports.reads) == 2
    assert len(fake.tables["integration_sync_jobs"]) == 2


def test_accounts_without_a_price_are_analyzed_and_accounts_being_ingested_are_retried_next_tick():
    fake = FakeRest()
    fake.tables["integration_sync_jobs"].append({"id": 1, "integration_slug": "amazon_ads",
                                                 "job_kind": "sp_search_terms", "external_account_id": "222",
                                                 "status": "running"})
    reports = FakeReports([_profile(profile_id="111", currency_code="MXN"), _profile(profile_id="222")])
    runner = _runner(fake, reports)

    summary = runner.plan()
    queued = [row for row in fake.tables["integration_sync_jobs"] if row["job_kind"] == JOB_KIND]
    assert (summary.analyses_queued, [row["external_account_id"] for row in queued]) == (1, ["111"])
    assert queued[0]["params"]["params"]["price"] is None

    fake.tables["integration_sync_jobs"][0]["status"] = "completed"
    assert runner.plan().analyses_queued == 1


def test_an_account_without_search_terms_has_nothing_to_analyze_whatever_its_currency():
    fake = FakeRest()
    reports = FakeReports([_profile(profile_id="111", currency_code="EUR")], rows=[])

    summary = _runner(fake, reports).plan()

    assert (summary.nothing_to_analyze, summary.analyses_queued) == (1, 0)


def test_an_account_that_breaks_the_payload_does_not_stop_the_others_or_retry_every_tick():
    class BrokenFirstAccount(FakeReports):
        def search_terms(self, option, start, end):
            if option.profile_id == "111":
                self.reads.append((option.profile_id, start, end))
                raise TypeError("float() argument must be a string or a real number, not 'NAType'")
            return super().search_terms(option, start, end)

    fake = FakeRest()
    reports = BrokenFirstAccount([_profile(profile_id="111"), _profile(profile_id="222")])
    runner = _runner(fake, reports)

    summary = runner.plan()
    runner.plan()

    assert summary.analyses_queued == 1 and len(summary.errors) == 1
    assert [row["external_account_id"] for row in fake.tables["integration_sync_jobs"]] == ["222"]
    assert [profile_id for profile_id, _, _ in reports.reads].count("111") == 1


# ── one job ───────────────────────────────────────────────────────────────────

def test_a_job_stores_the_answer_with_its_records_and_completes():
    fake, reports = FakeRest(), FakeReports([_profile()])
    job = _job(fake)

    outcome = _runner(fake, reports).execute(job)

    (analysis,) = fake.tables["ai_analyses"]
    assert (analysis["status"], analysis["result"], analysis["session_id"], analysis["trigger"]) == (
        "done", RESULT, "sess", "manual")
    assert [row["Search Term"] for row in analysis["negative_records"]] == ["cheap toy box"]
    stored_job = fake.tables["integration_sync_jobs"][0]
    assert (stored_job["status"], stored_job["rows_written"]) == ("completed", 2)
    assert outcome.analysis_id == analysis["id"] and not outcome.reused


def test_a_scheduled_analysis_waits_longer_than_the_page_and_holds_its_lease_for_that_wait():
    fake, reports = FakeRest(), FakeReports([_profile()])
    seen = []

    def ask(**call):
        seen.append((call["timeout_s"], fake.tables["integration_sync_jobs"][0]["lease_expires_at"]))
        return {"structured_output": RESULT}

    _runner(fake, reports, ask=ask).execute(_job(fake))

    ((timeout_s, lease_expires_at),) = seen
    # A little past the provider's own limit, so its timeout answer arrives instead of a dropped connection.
    assert timeout_s == BACKGROUND_TIMEOUT_SECONDS + PROVIDER_RESPONSE_MARGIN_SECONDS
    assert datetime.fromisoformat(lease_expires_at) - datetime.now(timezone.utc) > timedelta(seconds=timeout_s)


def test_a_manual_request_for_data_that_changed_since_fails_without_paying_an_analysis():
    fake, reports = FakeRest(), FakeReports([_profile()])
    calls = []
    job = _job(fake, params={"lang": "es", "input_digest": _digest_of(_JOB_PARAMS, rows=SEARCH_ROWS[:1]),
                             "params": dict(_JOB_PARAMS)})

    _runner(fake, reports, ask=lambda **call: calls.append(call)).execute(job)

    stored_job = fake.tables["integration_sync_jobs"][0]
    assert calls == [] and fake.tables["ai_analyses"] == []
    assert (stored_job["status"], stored_job["error_message"]) == ("failed", DATA_CHANGED_ERROR)


def test_a_scheduled_analysis_whose_account_parameters_changed_is_skipped_without_calling_the_provider():
    fake, reports = FakeRest(), FakeReports([_profile()])
    fake.tables["ai_analysis_settings"].append({"module": "str", "subject_id": "111", "updated_by": "ana",
                                                "updated_at": "2026-09-15T11:30:00+00:00",
                                                "params": {**_JOB_PARAMS, "target_acos": 45}})
    calls = []

    outcome = _runner(fake, reports, ask=lambda **call: calls.append(call)).execute(
        _job(fake, trigger="scheduled_daily"))

    stored_job = fake.tables["integration_sync_jobs"][0]
    assert calls == [] and outcome.analysis_id is None
    assert (stored_job["status"], stored_job["warning"]) == ("completed", SUPERSEDED_WARNING)


def test_data_whose_analysis_failed_before_is_reported_instead_of_counted_as_covered():
    fake, reports = FakeRest(), FakeReports([_profile()])
    _runner(fake, reports).plan()
    fake.tables["integration_sync_jobs"][0]["status"] = "failed"

    summary = _runner(fake, reports).plan()

    assert (summary.analyses_queued, summary.already_covered) == (0, 0)
    assert summary.errors == [f"111: {FAILED_BEFORE_NOTE}"]


def test_a_job_for_data_already_analyzed_completes_without_calling_the_provider():
    fake, reports = FakeRest(), FakeReports([_profile()])
    _runner(fake, reports).execute(_job(fake, id=8))
    calls = []

    outcome = _runner(fake, reports, ask=lambda **call: calls.append(call)).execute(_job(fake, id=9))

    assert calls == [] and outcome.reused
    assert fake.tables["integration_sync_jobs"][1]["warning"] == REUSED_WARNING


@pytest.mark.parametrize("error, retryable", [
    (client.ProviderDown("provider down"), True),
    (client.QuotaExceeded("quota", 300), True),
])
def test_provider_failures_mark_the_analysis_failed_and_retry_the_job(error, retryable):
    fake, reports = FakeRest(), FakeReports([_profile()])

    def failing(**call):
        raise error

    _runner(fake, reports, ask=failing).execute(_job(fake))

    (analysis,) = fake.tables["ai_analyses"]
    assert analysis["status"] == "failed"
    assert fake.tables["integration_sync_jobs"][0]["status"] == ("retrying" if retryable else "failed")


def test_an_answer_without_the_agreed_shape_is_a_retryable_failure():
    fake, reports = FakeRest(), FakeReports([_profile()])

    _runner(fake, reports, ask=lambda **call: {"text": "hola"}).execute(_job(fake))

    assert fake.tables["ai_analyses"][0]["status"] == "failed"
    assert fake.tables["integration_sync_jobs"][0]["status"] == "retrying"


def test_a_job_for_an_account_no_longer_active_fails_without_retrying():
    fake, reports = FakeRest(), FakeReports([_profile(status="needs_reauth")])

    _runner(fake, reports).execute(_job(fake))

    assert fake.tables["ai_analyses"] == []
    assert fake.tables["integration_sync_jobs"][0]["status"] == "failed"


def test_a_failed_run_of_the_same_data_is_restarted_instead_of_duplicated():
    fake, reports = FakeRest(), FakeReports([_profile()])

    def failing(**call):
        raise client.ProviderDown("down")

    _runner(fake, reports, ask=failing).execute(_job(fake, id=8))
    _runner(fake, reports).execute(_job(fake, id=9))

    (analysis,) = fake.tables["ai_analyses"]
    assert (analysis["status"], analysis["job_id"]) == ("done", 9)


def test_the_store_refuses_to_restart_a_finished_analysis():
    fake, reports = FakeRest(), FakeReports([_profile()])
    _runner(fake, reports).execute(_job(fake))
    analysis = fake.tables["ai_analyses"][0]
    new = NewAnalysis(module="str", subject_id="111", window_start=date(2026, 8, 16), window_end=date(2026, 9, 14),
                      lang="es", params={}, params_digest="p", input_digest=analysis["input_digest"],
                      agent_version=analysis["agent_version"], trigger="manual", requested_by="ana", job_id=10,
                      source_last_success_at=None, negative_records=[], harvest_records=[], model="opus")

    with pytest.raises(StoreError):
        AiAnalysisStore(fake).start(new)


def test_the_store_reads_the_newest_finished_analysis_and_the_history_without_the_current_one():
    fake = FakeRest()
    for analysis_id in (1, 2, 3):
        fake.tables["ai_analyses"].append({"id": analysis_id, "module": "str", "subject_id": "111", "status": "done",
                                           "input_digest": "same" if analysis_id < 3 else "other",
                                           "finished_at": f"2026-09-1{analysis_id}T10:00:00+00:00"})
    store = AiAnalysisStore(fake)

    assert isinstance(store.done_for_input("str", "111", "same"), StoredAnalysis)
    assert [analysis.id for analysis in store.history("str", "111", limit=5, exclude_id=3)] == [1, 2]


# ── the worker loop ───────────────────────────────────────────────────────────

def test_a_tick_plans_claims_up_to_the_free_slots_and_writes_a_heartbeat(monkeypatch):
    fake = FakeRest()
    fake.claimable = [dict(id=job_id, job_kind=JOB_KIND, status="running", external_account_id="111")
                      for job_id in (1, 2, 3)]
    executed = []
    monkeypatch.setattr("core.ai_analysis.worker.build_job", lambda rest: _RecordingJob(executed))
    worker = AnalysisWorker(rest_factory=lambda: fake, concurrency=2, clock=lambda: NOW)

    summary = worker.tick()
    worker.wait_for_running()

    assert summary["jobs_claimed"] == 2
    assert sorted(executed) == [1, 2]
    (heartbeat,) = fake.tables["integration_worker_heartbeats"]
    assert (heartbeat["worker_name"], heartbeat["last_tick_at"]) == (WORKER_NAME, NOW.isoformat())


def test_shutdown_hands_running_jobs_back_to_the_queue(monkeypatch):
    fake = FakeRest()
    fake.tables["integration_sync_jobs"].append({"id": 5, "status": "running", "lease_holder": "me"})
    monkeypatch.setattr("core.ai_analysis.worker.build_job", lambda rest: _RecordingJob([]))
    worker = AnalysisWorker(rest_factory=lambda: fake, concurrency=2, clock=lambda: NOW)
    worker._running = {5: None}

    worker.release_running()

    assert (fake.tables["integration_sync_jobs"][0]["status"], fake.tables["integration_sync_jobs"][0]["lease_holder"]) \
        == ("pending", "")


class _RecordingJob:
    def __init__(self, executed):
        self._executed = executed

    def plan(self, profile_ids=None):
        from core.ai_analysis.str_analysis_job import PlanSummary
        return PlanSummary()

    def execute(self, job):
        from core.ai_analysis.str_analysis_job import JobOutcome
        self._executed.append(job.id)
        return JobOutcome(job.id, None, reused=False)

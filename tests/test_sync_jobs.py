"""Generic sync job store over a fake PostgREST. No network."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from core.integrations.store import StoreError
from core.integrations.sync_jobs import (
    JOBS_TABLE,
    RETRY_DELAYS_MIN,
    ManualRefresh,
    NewSyncJob,
    SyncJob,
    SyncJobStore,
    sanitize_error,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


class _FakeRest:
    def __init__(self, *, select_rows=None, rpc_answers=None, insert_ignore_answer=True, fail_rpc=False):
        self._select_rows = list(select_rows or [])
        self._rpc_answers = dict(rpc_answers or {})
        self._insert_ignore_answer = insert_ignore_answer
        self._fail_rpc = fail_rpc
        self.selects: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, dict, dict]] = []
        self.inserts: list[tuple[str, dict, str]] = []
        self.rpcs: list[tuple[str, dict]] = []

    def select(self, table, params):
        self.selects.append((table, params))
        return self._select_rows.pop(0) if self._select_rows else []

    def update(self, table, params, changes, stamp=True):
        self.updates.append((table, params, changes))

    def insert_ignore(self, table, row, on_conflict, *, timeout_s=8):
        self.inserts.append((table, row, on_conflict))
        return self._insert_ignore_answer

    def rpc(self, name, args, *, timeout_s=8):
        self.rpcs.append((name, args))
        if self._fail_rpc:
            raise ConnectionError("gateway down")
        return self._rpc_answers.get(name)


def _row(**overrides) -> dict:
    row = {
        "id": 41, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms",
        "trigger": "scheduled_daily", "account_id": 3, "connection_id": None,
        "external_account_id": "e2e-profile-1", "cliente": "cliente-demo", "account_name": "Demo Seller",
        "marketplace": "MX", "region": "NA", "window_start": "2026-08-31", "window_end": "2026-09-13",
        "local_day": "2026-09-14", "status": "running", "phase": "requesting", "attempts": 0,
        "max_attempts": 3, "next_attempt_at": "2026-09-14T10:00:00+00:00",
        "deadline_at": "2026-09-15T06:00:00+00:00", "lease_holder": "worker-a",
        "lease_expires_at": "2026-09-14T12:15:00.12345+00:00", "rows_written": None, "warning": "",
        "error_class": "", "error_message": "", "attempt_log": [], "requested_by": "scheduler",
        "retry_of": None, "dedupe_key": "amazon_ads:e2e-profile-1:day:2026-09-14",
        "created_at": "2026-09-14T10:00:00+00:00", "started_at": "2026-09-14T12:00:00+00:00",
        "finished_at": None, "updated_at": "2026-09-14T12:00:00+00:00",
    }
    row.update(overrides)
    return row


def _job(**overrides) -> SyncJob:
    return SyncJob.from_row(_row(**overrides))


def test_from_row_parses_dates_timestamps_and_optionals():
    job = _job()

    assert job.window_start == date(2026, 8, 31)
    assert job.local_day == date(2026, 9, 14)
    assert job.lease_expires_at == datetime(2026, 9, 14, 12, 15, 0, 123450, tzinfo=timezone.utc)
    assert job.connection_id is None and job.account_id == 3
    assert job.finished_at is None
    assert job.attempt_log == ()
    assert job.is_open is True
    assert _job(status="failed").is_open is False


def test_from_row_treats_naive_timestamps_as_utc():
    job = _job(created_at="2026-09-14T10:00:00")
    assert job.created_at.tzinfo is timezone.utc


def test_enqueue_inserts_ignoring_duplicate_dedupe_keys():
    rest = _FakeRest(insert_ignore_answer=False)
    new_job = NewSyncJob(
        integration_slug="amazon_ads", job_kind="sp_search_terms", trigger="backfill",
        external_account_id="e2e-profile-1", account_id=None, connection_id=5, cliente="cliente-demo",
        account_name="Demo Seller", marketplace="US", region="NA", window_start=date(2026, 7, 11),
        window_end=date(2026, 9, 13), local_day=date(2026, 9, 14),
        deadline_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc), max_attempts=6,
        dedupe_key="amazon_ads:e2e-profile-1:backfill",
    )

    assert SyncJobStore(rest).enqueue(new_job) is False

    table, row, on_conflict = rest.inserts[0]
    assert (table, on_conflict) == (JOBS_TABLE, "dedupe_key")
    assert row["window_start"] == "2026-07-11"
    assert row["deadline_at"] == "2026-09-15T12:00:00+00:00"
    assert row["requested_by"] == "scheduler"
    assert "status" not in row


def test_claim_due_calls_the_claim_function_and_parses_jobs():
    rest = _FakeRest(rpc_answers={"claim_sync_jobs": [_row(id=1), _row(id=2, trigger="manual")]})

    jobs = SyncJobStore(rest).claim_due("worker-a", 20, 900)

    assert rest.rpcs == [("claim_sync_jobs", {"p_holder": "worker-a", "p_limit": 20, "p_lease_seconds": 900})]
    assert [job.id for job in jobs] == [1, 2]


def test_claim_due_with_nothing_due_is_empty():
    assert SyncJobStore(_FakeRest(rpc_answers={"claim_sync_jobs": []})).claim_due("w", 5, 60) == []


def test_set_phase_can_extend_the_lease():
    rest = _FakeRest()
    SyncJobStore(rest).set_phase(41, "waiting", extend_lease_seconds=900)

    table, params, changes = rest.updates[0]
    assert (table, params) == (JOBS_TABLE, {"id": "eq.41"})
    assert changes["phase"] == "waiting"
    assert datetime.fromisoformat(changes["lease_expires_at"]) > datetime.now(timezone.utc)


def test_set_phase_rejects_unknown_phase():
    with pytest.raises(ValueError):
        SyncJobStore(_FakeRest()).set_phase(41, "downloading")


def test_retryable_failure_schedules_retry_with_first_delay():
    rest = _FakeRest()

    updated = SyncJobStore(rest).record_attempt_failure(
        _job(), error_class="AdsApiError", message="HTTP 500", retryable=True, now=NOW)

    assert updated.status == "retrying"
    assert updated.attempts == 1
    assert updated.next_attempt_at == NOW + timedelta(minutes=RETRY_DELAYS_MIN[0])
    assert updated.lease_holder == "" and updated.lease_expires_at is None
    assert updated.finished_at is None and updated.phase == ""
    assert updated.attempt_log == (
        {"attempt": 1, "at": NOW.isoformat(), "error_class": "AdsApiError", "message": "HTTP 500"},)
    changes = rest.updates[0][2]
    assert changes["status"] == "retrying"
    assert changes["next_attempt_at"] == (NOW + timedelta(minutes=5)).isoformat()
    assert changes["lease_expires_at"] is None
    assert changes["attempt_log"] == list(updated.attempt_log)


def test_later_attempts_use_growing_delays_capped_at_the_last():
    store = SyncJobStore(_FakeRest())
    far_deadline = "2026-09-20T00:00:00+00:00"

    third = store.record_attempt_failure(
        _job(attempts=2, max_attempts=8, deadline_at=far_deadline),
        error_class="X", message="m", retryable=True, now=NOW)
    seventh = store.record_attempt_failure(
        _job(attempts=6, max_attempts=8, deadline_at=far_deadline),
        error_class="X", message="m", retryable=True, now=NOW)

    assert third.next_attempt_at == NOW + timedelta(minutes=30)
    assert seventh.next_attempt_at == NOW + timedelta(minutes=RETRY_DELAYS_MIN[-1])


def test_failure_on_last_attempt_is_final():
    rest = _FakeRest()
    previous_log = [{"attempt": 1, "at": "t1", "error_class": "X", "message": "a"},
                    {"attempt": 2, "at": "t2", "error_class": "X", "message": "b"}]

    updated = SyncJobStore(rest).record_attempt_failure(
        _job(attempts=2, max_attempts=3, attempt_log=previous_log),
        error_class="AdsApiError", message="HTTP 500", retryable=True, now=NOW)

    assert updated.status == "failed"
    assert updated.finished_at == NOW
    assert len(updated.attempt_log) == 3
    assert rest.updates[0][2]["finished_at"] == NOW.isoformat()
    assert "next_attempt_at" not in rest.updates[0][2]


def test_failure_whose_retry_would_miss_the_deadline_is_final():
    updated = SyncJobStore(_FakeRest()).record_attempt_failure(
        _job(deadline_at=(NOW + timedelta(minutes=4)).isoformat()),
        error_class="AdsApiError", message="HTTP 500", retryable=True, now=NOW)
    assert updated.status == "failed"


def test_non_retryable_failure_is_final_on_first_attempt():
    updated = SyncJobStore(_FakeRest()).record_attempt_failure(
        _job(max_attempts=8), error_class="NeedsReauth", message="invalid_grant", retryable=False, now=NOW)
    assert updated.status == "failed"
    assert updated.attempts == 1


def test_failure_message_is_truncated():
    updated = SyncJobStore(_FakeRest()).record_attempt_failure(
        _job(), error_class="X", message="x" * 900, retryable=True, now=NOW)
    assert len(updated.error_message) == 500


def test_complete_releases_dedupe_key_for_one_off_triggers():
    for trigger in ("backfill", "manual", "retry"):
        rest = _FakeRest()
        SyncJobStore(rest).complete(_job(trigger=trigger), rows_written=120, now=NOW)
        changes = rest.updates[0][2]
        assert changes["dedupe_key"] is None, trigger
        assert changes["status"] == "completed"
        assert changes["rows_written"] == 120
        assert changes["finished_at"] == NOW.isoformat()


def test_complete_keeps_dedupe_key_for_scheduled_jobs():
    rest = _FakeRest()
    SyncJobStore(rest).complete(_job(trigger="scheduled_daily"), rows_written=0,
                                warning="día vacío", now=NOW)
    changes = rest.updates[0][2]
    assert "dedupe_key" not in changes
    assert changes["warning"] == "día vacío"
    assert changes["lease_holder"] == "" and changes["lease_expires_at"] is None


def test_fail_expired_marks_queued_jobs_past_deadline():
    rest = _FakeRest(select_rows=[[{"id": 5}, {"id": 8}]])

    assert SyncJobStore(rest).fail_expired(NOW) == 2

    table, params = rest.selects[0]
    assert params["status"] == "in.(pending,retrying)"
    assert params["deadline_at"] == f"lte.{NOW.isoformat()}"
    _, update_params, changes = rest.updates[0]
    assert update_params == {"id": "in.(5,8)", "status": "in.(pending,retrying)"}
    assert changes["status"] == "failed" and changes["error_class"] == "deadline"


def test_fail_expired_without_candidates_writes_nothing():
    rest = _FakeRest(select_rows=[[]])
    assert SyncJobStore(rest).fail_expired(NOW) == 0
    assert rest.updates == []


class _TableRest:
    """A PostgREST stand-in that applies eq/in/lt/lte filters to one in-memory table."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def select(self, table, params):
        return [dict(row) for row in self.rows if _row_matches(row, params)]

    def update(self, table, params, changes, stamp=True):
        for row in self.rows:
            if _row_matches(row, params):
                row.update(changes)


def _row_matches(row: dict, params: dict) -> bool:
    for column, expression in params.items():
        if column in ("select", "order", "limit"):
            continue
        operator, _, operand = expression.partition(".")
        value = row.get(column)
        if operator == "eq":
            matched = value is not None and str(value) == operand
        elif operator == "in":
            matched = value is not None and str(value) in operand.strip("()").split(",")
        elif operator in ("lt", "lte"):
            if value is None:
                return False
            left, right = datetime.fromisoformat(value), datetime.fromisoformat(operand)
            matched = left < right if operator == "lt" else left <= right
        else:
            raise AssertionError(f"unsupported filter {column}={expression}")
        if not matched:
            return False
    return True


def _stored_job(job_id: int, status: str, *, deadline_ago: timedelta, lease_ago: timedelta | None) -> dict:
    return {
        "id": job_id, "status": status, "phase": "waiting" if status == "running" else "",
        "deadline_at": (NOW - deadline_ago).isoformat(),
        "lease_expires_at": (NOW - lease_ago).isoformat() if lease_ago is not None else None,
        "lease_holder": "worker-a" if lease_ago is not None else "",
    }


def test_fail_expired_fails_a_running_job_abandoned_past_its_deadline_grace():
    rows = [
        _stored_job(1, "running", deadline_ago=timedelta(hours=4), lease_ago=timedelta(minutes=20)),
        _stored_job(2, "running", deadline_ago=timedelta(hours=3), lease_ago=timedelta(minutes=20)),
        _stored_job(3, "running", deadline_ago=timedelta(hours=5), lease_ago=-timedelta(minutes=10)),
        _stored_job(4, "pending", deadline_ago=timedelta(minutes=1), lease_ago=None),
        _stored_job(5, "completed", deadline_ago=timedelta(hours=9), lease_ago=None),
    ]

    failed = SyncJobStore(_TableRest(rows)).fail_expired(NOW)

    assert failed == 2
    assert {row["id"]: row["status"] for row in rows} == {
        1: "failed", 2: "running", 3: "running", 4: "failed", 5: "completed"}
    abandoned = rows[0]
    assert abandoned["error_class"] == "deadline" and abandoned["phase"] == ""
    assert abandoned["lease_holder"] == "" and abandoned["lease_expires_at"] is None
    assert abandoned["finished_at"] == NOW.isoformat()


def test_fail_expired_leaves_a_running_job_reclaimed_after_the_select():
    rows = [_stored_job(1, "running", deadline_ago=timedelta(hours=4), lease_ago=timedelta(minutes=20))]
    rest = _TableRest(rows)
    real_update = rest.update

    def update_after_a_reclaim(table, params, changes, stamp=True):
        rows[0]["lease_expires_at"] = (NOW + timedelta(minutes=15)).isoformat()
        real_update(table, params, changes, stamp)

    rest.update = update_after_a_reclaim
    SyncJobStore(rest).fail_expired(NOW)

    assert rows[0]["status"] == "running"


def test_worker_writes_never_reopen_a_job_an_admin_already_closed():
    rows = [{"id": 41, "status": "cancelled", "error_message": "cancelada por admin-demo"},
            {"id": 42, "status": "running", "error_message": ""}]
    store = SyncJobStore(_TableRest(rows))

    store.record_attempt_failure(_job(), error_class="AdsApiError", message="HTTP 500", retryable=True, now=NOW)
    store.complete(_job(), rows_written=10, now=NOW)
    store.record_attempt_failure(_job(id=42), error_class="AdsApiError", message="HTTP 500", retryable=True, now=NOW)

    assert rows[0] == {"id": 41, "status": "cancelled", "error_message": "cancelada por admin-demo"}
    assert rows[1]["status"] == "retrying"


def test_cancel_open_for_profile_cancels_every_open_job():
    rest = _FakeRest(select_rows=[[{"id": 1}, {"id": 2}, {"id": 3}]])

    count = SyncJobStore(rest).cancel_open_for_profile("amazon_ads", "e2e-profile-1", "perfil inactivo")

    assert count == 3
    params = rest.selects[0][1]
    assert params["external_account_id"] == "eq.e2e-profile-1"
    assert params["status"] == "in.(pending,running,retrying)"
    changes = rest.updates[0][2]
    assert changes["status"] == "cancelled"
    assert changes["error_message"] == "perfil inactivo"


def test_has_open_checks_open_statuses_for_profile_and_kind():
    rest = _FakeRest(select_rows=[[{"id": 1}], []])
    store = SyncJobStore(rest)

    assert store.has_open("amazon_ads", "portfolio_names", "e2e-profile-1") is True
    assert store.has_open("amazon_ads", "portfolio_names", "e2e-profile-1") is False
    params = rest.selects[0][1]
    assert params["job_kind"] == "eq.portfolio_names"
    assert params["status"] == "in.(pending,running,retrying)"


def test_list_recent_builds_filters_and_keyset_page():
    rest = _FakeRest(select_rows=[[_row(id=9), _row(id=8)]])
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)

    jobs = SyncJobStore(rest).list_recent(
        slugs=("amazon_ads",), statuses=("failed", "retrying"), external_account_id="e2e-profile-1",
        since=since, only_problems=True, limit=50, before_id=10)

    params = rest.selects[0][1]
    assert params["order"] == "id.desc" and params["limit"] == "50"
    assert params["integration_slug"] == "in.(amazon_ads)"
    assert params["status"] == "in.(failed,retrying)"
    assert params["created_at"] == f"gte.{since.isoformat()}"
    assert params["id"] == "lt.10"
    assert "failed" in params["or"] and "warning.neq" in params["or"]
    assert [job.id for job in jobs] == [9, 8]


def test_list_recent_without_filters_only_orders_and_limits():
    rest = _FakeRest(select_rows=[[]])
    SyncJobStore(rest).list_recent()
    assert rest.selects[0][1] == {"select": "*", "order": "id.desc", "limit": "200"}


def test_get_and_latest_for_profile_return_none_when_missing():
    store = SyncJobStore(_FakeRest(select_rows=[[], [_row(id=77)]]))
    assert store.get(1) is None
    assert store.latest_for_profile("e2e-profile-1").id == 77


def test_counts_since_groups_by_status():
    rest = _FakeRest(select_rows=[[{"status": "failed"}, {"status": "completed"}, {"status": "failed"}]])
    assert SyncJobStore(rest).counts_since(NOW) == {"failed": 2, "completed": 1}


def test_request_manual_refresh_maps_the_function_answer():
    rest = _FakeRest(rpc_answers={
        "request_manual_refresh": [{"job_id": 12, "created": False, "reason": "already_running"}]})

    outcome = SyncJobStore(rest).request_manual_refresh("e2e-profile-1", "juan")

    assert outcome == ManualRefresh(job_id=12, created=False, reason="already_running")
    assert rest.rpcs[0] == ("request_manual_refresh", {"p_profile_id": "e2e-profile-1", "p_requested_by": "juan"})


def test_request_manual_refresh_for_unavailable_profile_has_no_job():
    rest = _FakeRest(rpc_answers={
        "request_manual_refresh": [{"job_id": None, "created": False, "reason": "profile_unavailable"}]})
    assert SyncJobStore(rest).request_manual_refresh("gone", "juan") == ManualRefresh(
        job_id=None, created=False, reason="profile_unavailable")


def test_app_side_actions_raise_store_error_with_spanish_message():
    store = SyncJobStore(_FakeRest(fail_rpc=True))
    for action in (lambda: store.request_manual_refresh("p", "juan"),
                   lambda: store.retry(1, "juan"),
                   lambda: store.cancel(1, "juan")):
        with pytest.raises(StoreError) as raised:
            action()
        assert str(raised.value).startswith("No se pudo")


def test_retry_and_cancel_return_function_answers():
    rest = _FakeRest(rpc_answers={"retry_sync_job": 99, "cancel_sync_job": True})
    store = SyncJobStore(rest)

    assert store.retry(41, "juan") == 99
    assert store.cancel(41, "juan") is True
    assert rest.rpcs == [("retry_sync_job", {"p_job_id": 41, "p_actor": "juan"}),
                         ("cancel_sync_job", {"p_job_id": 41, "p_actor": "juan"})]


def test_retry_of_a_job_that_is_not_retryable_is_none():
    assert SyncJobStore(_FakeRest(rpc_answers={"retry_sync_job": None})).retry(41, "juan") is None


def test_sanitize_error_strips_query_strings_tokens_and_long_hex():
    exc = RuntimeError(
        "403 Client Error: Forbidden for url: https://reports.example.com/r/abc.json.gz?X-Amz-Signature=deadbeef&X-Amz-Credential=x "
        "headers Authorization: Bearer Atza|IwEBIsecretvalue refresh_token=Atzr|topsecret "
        "digest 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 report 3f1b2c9e-aaaa-bbbb-cccc-1234567890ab"
    )

    error_class, message = sanitize_error(exc)

    assert error_class == "RuntimeError"
    assert "X-Amz-Signature" not in message and "https://reports.example.com/r/abc.json.gz" in message
    assert "IwEBIsecretvalue" not in message and "topsecret" not in message
    assert "9f86d081884c7d659a2feaa0c55ad015" not in message
    assert "3f1b2c9e-aaaa-bbbb-cccc-1234567890ab" in message


def test_sanitize_error_caps_length_and_collapses_whitespace():
    error_class, message = sanitize_error(ValueError("line one\n\n   line two " + "y" * 800))
    assert error_class == "ValueError"
    assert message.startswith("line one line two")
    assert len(message) == 500

"""Sync alerts: pure rules plus the loader that must never raise. No network."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import requests

from core.integrations.store import Connection
from core.integrations.sync_alerts import (
    CONSENT_EXPIRING,
    ERROR,
    FAILED_TODAY,
    FIRST_LOAD_FAILED,
    NEEDS_REAUTH_KIND,
    STALE_DATA,
    STUCK,
    WARNING,
    WORKER_SILENT,
    build_alerts,
    load_alerts,
)
from core.integrations.sync_jobs import SyncJob

# 17:00 UTC is 10:00 in America/Los_Angeles (PDT): past the 09:00 data promise.
NOW = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)


def _job(**overrides) -> SyncJob:
    row = {
        "id": 1, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms",
        "trigger": "scheduled_daily", "external_account_id": "e2e-profile-1", "cliente": "cliente-demo",
        "account_name": "Demo Seller", "marketplace": "MX", "region": "NA", "status": "failed",
        "phase": "", "attempts": 3, "max_attempts": 3, "attempt_log": [],
        "deadline_at": "2026-09-15T06:00:00+00:00", "finished_at": "2026-09-14T15:00:00+00:00",
    }
    row.update(overrides)
    return SyncJob.from_row(row)


def _profile(**overrides) -> dict:
    row = {
        "profile_id": "e2e-profile-1", "cliente": "cliente-demo", "account_name": "Demo Seller",
        "region": "NA", "country_code": "US", "timezone": "America/Los_Angeles", "status": "active",
        "backfill_done_at": "2026-09-01T10:00:00+00:00", "refreshed_on": "2026-09-14",
        "last_success_at": "2026-09-14T11:00:00+00:00",
    }
    row.update(overrides)
    return row


def _connection(**overrides) -> Connection:
    fields = {
        "id": 5, "slug": "amazon_ads", "client": "cliente-demo", "external_account_id": "lwa-user",
        "external_name": "", "marketplace": "US CA", "status": "activo", "connected_by": "juan",
        "last_sync_at": "", "last_error": "", "consent_date": "2026-01-10",
    }
    fields.update(overrides)
    return Connection(**fields)


def _fresh_heartbeat() -> dict:
    return {"worker_name": "amazon_ads", "last_tick_at": (NOW - timedelta(minutes=1)).isoformat()}


def _alerts(**inputs):
    defaults = {"failed_jobs": [], "stuck_jobs": [], "profiles": [], "connections": [],
                "heartbeat": _fresh_heartbeat(), "now": NOW}
    defaults.update(inputs)
    return build_alerts(**defaults)


def test_healthy_state_has_no_alerts():
    assert _alerts(profiles=[_profile()], connections=[_connection()]) == []


def test_failed_job_in_last_24_hours_is_an_error_with_job_id():
    [alert] = _alerts(failed_jobs=[_job(id=33)])

    assert alert.kind == FAILED_TODAY and alert.severity == ERROR
    assert alert.job_id == 33
    assert alert.subject == "cliente-demo" and alert.marketplaces == "MX"
    assert "3 intentos" in alert.detail


@pytest.mark.parametrize("job_kind, label", [("sp_ad_groups", "ad groups SP"), ("sp_negatives", "negativos SP")])
def test_a_failed_sp_structure_listing_names_what_it_lists(job_kind, label):
    [alert] = _alerts(failed_jobs=[_job(job_kind=job_kind)])

    assert alert.detail == f"Falló la actualización de {label} después de 3 intentos."


def test_failure_older_than_24_hours_is_ignored():
    assert _alerts(failed_jobs=[_job(finished_at="2026-09-13T16:00:00+00:00")]) == []


def test_later_completion_for_same_account_and_kind_clears_the_failure():
    failed = _job(id=1, finished_at="2026-09-14T10:00:00+00:00")
    completed = _job(id=2, status="completed", finished_at="2026-09-14T12:00:00+00:00")
    assert _alerts(failed_jobs=[failed, completed]) == []


def test_newer_open_job_for_same_account_and_kind_holds_the_failure_back():
    failed = _job(id=1, finished_at="2026-09-14T10:00:00+00:00")
    queued_retry = _job(id=2, trigger="retry", retry_of=1, status="pending", finished_at=None)
    assert _alerts(failed_jobs=[failed], open_jobs=[queued_retry]) == []

    older_open = _job(id=0, status="retrying", finished_at=None)
    other_account = _job(id=3, status="pending", finished_at=None, external_account_id="other-profile")
    assert [alert.job_id for alert in _alerts(failed_jobs=[failed], open_jobs=[older_open, other_account])] == [1]


def test_only_the_latest_failure_of_an_account_and_kind_is_an_alert():
    failed = _job(id=1, finished_at="2026-09-14T10:00:00+00:00")
    failed_retry = _job(id=2, trigger="retry", retry_of=1, finished_at="2026-09-14T12:00:00+00:00")
    assert [alert.job_id for alert in _alerts(failed_jobs=[failed, failed_retry])] == [2]


def test_retry_queued_from_a_failed_first_load_shows_no_alert_until_it_ends():
    failed = _backfill(id=12, finished_at="2026-09-14T15:00:00+00:00")
    queued_retry = _job(id=31, trigger="retry", retry_of=12, status="pending", finished_at=None)
    alerts = _alerts(failed_jobs=[failed], open_jobs=[queued_retry], first_load_jobs=[failed, queued_retry],
                     profiles=[_first_load_profile()])
    assert alerts == []


def test_completion_in_the_same_tick_as_the_failure_clears_it():
    completed = _job(id=500, status="completed", finished_at="2026-09-14T15:00:00+00:00")
    failed_retry = _job(id=510, trigger="retry", finished_at="2026-09-14T15:00:00+00:00")
    assert _alerts(failed_jobs=[completed, failed_retry]) == []


def test_completion_before_the_failure_does_not_clear_it():
    completed = _job(id=2, status="completed", finished_at="2026-09-14T08:00:00+00:00")
    failed = _job(id=1, finished_at="2026-09-14T10:00:00+00:00")
    assert [alert.job_id for alert in _alerts(failed_jobs=[completed, failed])] == [1]


def test_completion_of_another_kind_does_not_clear_the_failure():
    failed = _job(id=1, finished_at="2026-09-14T10:00:00+00:00")
    other_kind = _job(id=2, status="completed", job_kind="portfolio_names",
                      finished_at="2026-09-14T12:00:00+00:00")
    assert [alert.kind for alert in _alerts(failed_jobs=[failed, other_kind])] == [FAILED_TODAY]


def test_running_job_with_lease_expired_over_15_minutes_is_stuck():
    stuck = _job(id=7, status="running", phase="requesting", finished_at=None,
                 started_at=(NOW - timedelta(minutes=40)).isoformat(),
                 lease_expires_at=(NOW - timedelta(minutes=16)).isoformat())
    [alert] = _alerts(stuck_jobs=[stuck])
    assert alert.kind == STUCK and alert.job_id == 7 and alert.severity == ERROR


def test_recently_expired_lease_is_not_stuck_yet():
    running = _job(status="running", phase="saving", finished_at=None,
                   started_at=(NOW - timedelta(minutes=20)).isoformat(),
                   lease_expires_at=(NOW - timedelta(minutes=10)).isoformat())
    assert _alerts(stuck_jobs=[running]) == []


def test_saving_for_more_than_4_hours_is_stuck_even_with_live_lease():
    running = _job(status="running", phase="saving", finished_at=None,
                   started_at=(NOW - timedelta(hours=5)).isoformat(),
                   lease_expires_at=(NOW + timedelta(minutes=10)).isoformat())
    assert [alert.kind for alert in _alerts(stuck_jobs=[running])] == [STUCK]


def test_waiting_for_amazon_is_never_stuck():
    waiting = _job(status="running", phase="waiting", finished_at=None,
                   started_at=(NOW - timedelta(hours=6)).isoformat(),
                   lease_expires_at=(NOW - timedelta(hours=5)).isoformat())
    assert _alerts(stuck_jobs=[waiting]) == []


def test_profile_not_refreshed_today_after_9am_local_is_stale():
    [alert] = _alerts(profiles=[_profile(refreshed_on="2026-09-13")])

    assert alert.kind == STALE_DATA and alert.severity == WARNING
    assert alert.subject == "cliente-demo" and alert.marketplaces == "US"
    assert "13/09/2026" in alert.detail
    assert alert.since == datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)


def test_stale_profile_before_9am_local_is_not_an_alert_yet():
    early = datetime(2026, 9, 14, 15, 30, tzinfo=timezone.utc)  # 08:30 in Los Angeles
    assert _alerts(profiles=[_profile(refreshed_on="2026-09-13")], now=early,
                   heartbeat={"last_tick_at": early.isoformat()}) == []


def test_stale_profiles_of_one_account_group_their_countries():
    profiles = [
        _profile(profile_id="p-us", country_code="US", refreshed_on="2026-09-13"),
        _profile(profile_id="p-ca", country_code="CA", refreshed_on="2026-09-12"),
        _profile(profile_id="p-mx", country_code="MX", refreshed_on="2026-09-14"),
    ]
    [alert] = _alerts(profiles=profiles)
    assert alert.marketplaces == "CA US"
    assert "12/09/2026" in alert.detail


def test_profile_in_first_load_or_not_active_is_not_stale():
    profiles = [
        _profile(profile_id="first-load", backfill_done_at=None, refreshed_on=None),
        _profile(profile_id="reauth", status="needs_reauth", refreshed_on="2026-09-01"),
        _profile(profile_id="off", status="inactive", refreshed_on="2026-09-01"),
    ]
    assert _alerts(profiles=profiles) == []


def test_stale_uses_the_profile_timezone():
    tokyo = _profile(timezone="Asia/Tokyo", refreshed_on="2026-09-14")  # already 15 Sept 02:00 there
    assert _alerts(profiles=[tokyo]) == []
    tokyo_morning = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)  # 10:00 on 15 Sept in Tokyo
    [alert] = _alerts(profiles=[tokyo], now=tokyo_morning,
                      heartbeat={"last_tick_at": tokyo_morning.isoformat()})
    assert alert.kind == STALE_DATA


def test_old_heartbeat_is_worker_silent():
    heartbeat = {"last_tick_at": (NOW - timedelta(minutes=12)).isoformat()}
    [alert] = _alerts(heartbeat=heartbeat, profiles=[_profile(region="EU"), _profile(region="NA")])
    assert alert.kind == WORKER_SILENT and alert.severity == ERROR
    assert "12 min" in alert.detail
    assert alert.marketplaces == "EU NA"


def test_missing_heartbeat_alerts_only_with_active_profiles():
    assert [a.kind for a in _alerts(heartbeat=None, profiles=[_profile()])] == [WORKER_SILENT]
    assert _alerts(heartbeat=None, profiles=[_profile(status="inactive")]) == []


def test_connection_needing_reauth_is_an_error():
    [alert] = _alerts(connections=[_connection(status="needs_reauth")])
    assert alert.kind == NEEDS_REAUTH_KIND and alert.severity == ERROR
    assert alert.subject == "Autorización de juan"
    assert alert.connection_id == 5 and alert.marketplaces == "US CA"


def test_consent_inside_warning_window_is_a_warning():
    [alert] = _alerts(connections=[_connection(consent_date="2025-10-01")])
    assert alert.kind == CONSENT_EXPIRING and alert.severity == WARNING
    assert "01/10/2026" in alert.detail


def test_provider_without_consent_lifetime_never_expires():
    assert _alerts(connections=[_connection(slug="mercado_libre", consent_date="2025-10-01")]) == []


def _backfill(**overrides) -> SyncJob:
    return _job(**{"trigger": "backfill", "error_class": "AdsAccessDenied", "attempts": 1, **overrides})


def _first_load_profile(**overrides) -> dict:
    return _profile(**{"backfill_done_at": None, "refreshed_on": None, **overrides})


def test_failed_backfill_of_a_profile_without_first_load_is_an_error_days_later():
    failed = _backfill(id=12, finished_at="2026-09-09T10:00:00+00:00")

    [alert] = _alerts(first_load_jobs=[failed], profiles=[_first_load_profile()])

    assert alert.kind == FIRST_LOAD_FAILED and alert.severity == ERROR
    assert alert.job_id == 12
    assert alert.subject == "cliente-demo" and alert.marketplaces == "US"
    assert alert.detail == "La carga inicial no se completó: AdsAccessDenied."
    assert alert.since == datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)


def test_cancelled_backfill_is_a_failed_first_load_too():
    cancelled = _backfill(id=12, status="cancelled", error_class="", error_message="cancelada por admin-demo")
    [alert] = _alerts(first_load_jobs=[cancelled], profiles=[_first_load_profile()])
    assert alert.detail == "La carga inicial no se completó: cancelada."


def test_backfill_planned_again_after_the_failure_clears_the_alert():
    jobs = [_backfill(id=12), _backfill(id=30, status="pending", finished_at=None, error_class="")]
    assert _alerts(first_load_jobs=jobs, profiles=[_first_load_profile()]) == []


def test_retry_of_the_failed_backfill_carries_the_first_load():
    failed = _backfill(id=12)
    running_retry = _job(id=31, trigger="retry", retry_of=12, status="running", finished_at=None)
    assert _alerts(first_load_jobs=[failed, running_retry], profiles=[_first_load_profile()]) == []

    failed_retry = _job(id=31, trigger="retry", retry_of=12, status="failed", error_class="ReportFailed")
    [alert] = _alerts(first_load_jobs=[failed, failed_retry], profiles=[_first_load_profile()])
    assert (alert.job_id, alert.detail) == (31, "La carga inicial no se completó: ReportFailed.")


def test_retry_of_a_manual_refresh_is_not_a_first_load():
    failed = _backfill(id=12)
    manual_retry = _job(id=40, trigger="retry", retry_of=35, status="pending", finished_at=None)
    [alert] = _alerts(first_load_jobs=[failed, manual_retry], profiles=[_first_load_profile()])
    assert alert.job_id == 12


def test_failed_backfill_is_not_a_first_load_alert_once_loaded_or_disconnected():
    failed = _backfill(id=12)
    assert _alerts(first_load_jobs=[failed], profiles=[_profile()]) == []
    assert _alerts(first_load_jobs=[failed], profiles=[_first_load_profile(status="inactive")]) == []


def test_backfill_failed_today_is_reported_once_as_a_failed_first_load():
    failed = _backfill(id=12, finished_at="2026-09-14T15:00:00+00:00")
    alerts = _alerts(failed_jobs=[failed], first_load_jobs=[failed], profiles=[_first_load_profile()])
    assert [(alert.kind, alert.job_id) for alert in alerts] == [(FIRST_LOAD_FAILED, 12)]

    failed_retry = _job(id=31, trigger="retry", retry_of=12, status="failed", finished_at="2026-09-14T16:00:00+00:00")
    other_profile = _job(id=40, external_account_id="other-profile", finished_at="2026-09-14T16:00:00+00:00")
    alerts = _alerts(failed_jobs=[failed, failed_retry, other_profile], first_load_jobs=[failed, failed_retry],
                     profiles=[_first_load_profile()])
    assert sorted((alert.kind, alert.job_id) for alert in alerts) == [(FAILED_TODAY, 40), (FIRST_LOAD_FAILED, 31)]


def test_alerts_sort_errors_first_then_oldest_first():
    alerts = _alerts(
        failed_jobs=[_job(id=1, finished_at="2026-09-14T15:00:00+00:00", external_account_id="a"),
                     _job(id=2, finished_at="2026-09-14T09:00:00+00:00", external_account_id="b")],
        profiles=[_profile(refreshed_on="2026-09-13")],
        connections=[_connection(status="needs_reauth")],
    )
    assert [(alert.severity, alert.kind, alert.job_id) for alert in alerts] == [
        (ERROR, FAILED_TODAY, 2),
        (ERROR, FAILED_TODAY, 1),
        (ERROR, NEEDS_REAUTH_KIND, None),
        (WARNING, STALE_DATA, None),
    ]


class _FakeRest:
    def __init__(self, tables: dict, failing_table: str = ""):
        self._tables = tables
        self._failing_table = failing_table
        self.selects: list[tuple[str, dict]] = []

    def select(self, table, params):
        self.selects.append((table, params))
        if table == self._failing_table:
            raise requests.HTTPError("404 Client Error: relation does not exist")
        rows = self._tables.get(table, [])
        if "status" in params and table == "integration_sync_jobs":
            wanted = params["status"].removeprefix("eq.").removeprefix("in.(").rstrip(")").split(",")
            rows = [row for row in rows if row["status"] in wanted]
        return rows


def _job_row(**overrides) -> dict:
    row = {"id": 1, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "status": "failed",
           "external_account_id": "e2e-profile-1", "cliente": "cliente-demo", "marketplace": "MX",
           "attempts": 3, "max_attempts": 3, "attempt_log": [], "finished_at": "2026-09-14T15:00:00+00:00"}
    row.update(overrides)
    return row


def test_load_alerts_reads_every_source_and_builds_alerts():
    rest = _FakeRest({
        "integration_sync_jobs": [_job_row(id=4)],
        "ads_profile_sync": [_profile()],
        "integration_worker_heartbeats": [_fresh_heartbeat()],
        "integration_connections": [{"id": 5, "integration_slug": "amazon_ads", "cliente": "cliente-demo",
                                     "estado": "needs_reauth", "conectado_por": "juan", "marketplace": "US"}],
    })

    alerts, read_ok = load_alerts(rest, NOW)

    assert read_ok is True
    assert sorted(alert.kind for alert in alerts) == [FAILED_TODAY, NEEDS_REAUTH_KIND]
    finished_query = rest.selects[0][1]
    assert finished_query["finished_at"] == f"gte.{(NOW - timedelta(hours=24)).isoformat()}"


def test_load_alerts_reads_the_first_load_jobs_of_profiles_still_waiting_for_it():
    rest = _FakeRest({
        "integration_sync_jobs": [_job_row(id=12, trigger="backfill", error_class="AdsAccessDenied",
                                           finished_at="2026-09-10T15:00:00+00:00")],
        "ads_profile_sync": [_profile(profile_id="loaded"),
                             _profile(profile_id="e2e-profile-1", backfill_done_at=None, refreshed_on=None)],
        "integration_worker_heartbeats": [_fresh_heartbeat()],
    })

    alerts, read_ok = load_alerts(rest, NOW)

    assert read_ok is True
    assert [(alert.kind, alert.job_id) for alert in alerts] == [(FIRST_LOAD_FAILED, 12)]
    [first_load_query] = [params for table, params in rest.selects
                          if table == "integration_sync_jobs" and "trigger" in params]
    assert first_load_query["external_account_id"] == "in.(e2e-profile-1)"
    assert first_load_query["trigger"] == "in.(backfill,retry)"
    assert first_load_query["job_kind"] == "eq.sp_search_terms"


def test_load_alerts_skips_the_first_load_query_when_every_profile_is_loaded():
    rest = _FakeRest({"ads_profile_sync": [_profile()], "integration_worker_heartbeats": [_fresh_heartbeat()]})
    load_alerts(rest, NOW)
    assert not [params for table, params in rest.selects if "trigger" in params]


def test_load_alerts_never_raises_when_a_table_is_missing():
    rest = _FakeRest({}, failing_table="ads_profile_sync")
    assert load_alerts(rest, NOW) == ([], False)


def test_load_alerts_reports_failed_connection_read():
    rest = _FakeRest({"ads_profile_sync": [], "integration_worker_heartbeats": []},
                     failing_table="integration_connections")
    assert load_alerts(rest, NOW) == ([], False)


def test_a_silent_analysis_worker_is_an_error_and_a_host_without_one_is_not():
    stale = {"worker_name": "ai_analysis", "last_tick_at": (NOW - timedelta(minutes=12)).isoformat()}
    fresh = {"worker_name": "ai_analysis", "last_tick_at": (NOW - timedelta(minutes=1)).isoformat()}

    (alert,) = _alerts(profiles=[_profile()], analysis_heartbeat=stale)

    assert (alert.kind, alert.severity, alert.subject) == (WORKER_SILENT, ERROR, "Generador de análisis IA")
    assert "12 min" in alert.detail
    assert _alerts(profiles=[_profile()], analysis_heartbeat=fresh) == []
    assert _alerts(profiles=[_profile()], analysis_heartbeat=None) == []


def test_load_alerts_reads_both_worker_heartbeats():
    stale_analysis = {"worker_name": "ai_analysis", "last_tick_at": (NOW - timedelta(minutes=30)).isoformat()}
    rest = _FakeRest({"ads_profile_sync": [_profile()],
                      "integration_worker_heartbeats": [_fresh_heartbeat(), stale_analysis]})

    alerts, read_ok = load_alerts(rest, NOW)

    assert read_ok is True
    assert [(alert.kind, alert.subject) for alert in alerts] == [(WORKER_SILENT, "Generador de análisis IA")]

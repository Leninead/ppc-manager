"""Request log page: status labels, times in Argentina, pagination, actions and the sidebar count. No network."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest

from core.integrations import notice
from core.integrations.store import StoreError
from core.integrations.sync_alerts import ERROR, WARNING, SyncAlert
from core.integrations.sync_jobs import SyncJob
from core.ui import i18n
from modules.pages import request_log as page

# 15:30 UTC is 12:30 in Buenos Aires.
NOW = datetime(2026, 9, 14, 15, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _spanish(monkeypatch):
    monkeypatch.setattr(i18n, "current_lang", lambda: "es")


def _job(**overrides) -> SyncJob:
    row = {
        "id": 41, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms",
        "trigger": "scheduled_daily", "external_account_id": "demo-profile-1", "cliente": "cliente-demo",
        "account_name": "Demo Seller", "marketplace": "MX", "region": "NA", "status": "pending",
        "phase": "", "attempts": 0, "max_attempts": 8, "attempt_log": [],
        "window_start": "2026-08-31", "window_end": "2026-09-13",
        "created_at": "2026-09-14T10:00:00+00:00", "deadline_at": "2026-09-15T06:00:00+00:00",
    }
    row.update(overrides)
    return SyncJob.from_row(row)


@pytest.mark.parametrize("status, phase, expected", [
    ("pending", "", "En cola"),
    ("running", "requesting", "Pidiendo a Amazon"),
    ("running", "waiting", "Esperando a Amazon"),
    ("running", "saving", "Guardando"),
    ("running", "", "En curso"),
    ("retrying", "", "Reintentando"),
    ("completed", "", "Completada"),
    ("failed", "", "Fallida"),
    ("cancelled", "", "Cancelada"),
])
def test_status_label_names_every_status_and_phase(status, phase, expected):
    assert page.status_label(status, phase) == expected


def test_completed_search_terms_with_a_warning_reads_as_an_empty_day():
    warning = "día vacío: Amazon no devolvió términos para 2026-09-01"
    assert page.status_label("completed", "", warning, "sp_search_terms") == "Completada · día vacío"
    assert page.status_label("completed", "", "sin permiso para leer portfolios",
                             "portfolio_names") == "Completada · con aviso"


def test_a_campaign_report_job_closes_with_the_same_empty_day_reading():
    warning = "día vacío: Amazon no devolvió filas para 2026-09-01"
    assert page.status_label("completed", "", warning, "sp_campaigns") == "Completada · día vacío"
    assert page.status_label("completed", "", "sin permiso para leer campañas",
                             "campaign_entities") == "Completada · con aviso"


def test_status_label_in_english(monkeypatch):
    monkeypatch.setattr(i18n, "current_lang", lambda: "en")
    assert page.status_label("running", "waiting") == "Waiting for Amazon"
    assert page.status_label("completed", "", "día vacío", "sp_search_terms") == "Completed · empty day"


@pytest.mark.parametrize("status, warning, expected", [
    ("failed", "", "err"),
    ("retrying", "", "warn"),
    ("completed", "día vacío", "warn"),
    ("completed", "", "ok"),
    ("pending", "", "idle"),
    ("running", "", "idle"),
    ("cancelled", "", "idle"),
])
def test_status_kind_paints_failures_red_and_retries_amber(status, warning, expected):
    assert page.status_kind(status, warning) == expected


@pytest.mark.parametrize("seconds, expected", [
    (4, "4 s"), (59.9, "59 s"), (60, "1 min"), (600, "10 min"),
    (4 * 3600 + 40 * 60, "4 h 40 min"), (2 * 3600, "2 h"), (-5, "0 s"),
])
def test_format_elapsed_picks_the_largest_readable_unit(seconds, expected):
    assert page.format_elapsed(seconds) == expected


def test_duration_of_a_finished_job_is_start_to_finish():
    job = _job(status="completed", started_at="2026-09-14T10:00:00+00:00",
               finished_at="2026-09-14T10:22:30+00:00")
    assert page.duration_text(job, NOW) == "22 min"


def test_duration_of_a_running_job_counts_up_to_now():
    job = _job(status="running", phase="waiting", started_at="2026-09-14T15:18:00+00:00")
    assert page.duration_text(job, NOW) == "12 min · en curso"


def test_duration_of_a_retrying_job_says_it_is_waiting():
    job = _job(status="retrying", attempts=3, started_at="2026-09-14T10:00:00+00:00")
    assert page.duration_text(job, NOW) == "en espera"


def test_duration_of_a_job_that_never_started_is_a_dash():
    assert page.duration_text(_job(status="pending"), NOW) == "—"
    assert page.duration_text(_job(status="failed", finished_at="2026-09-14T12:00:00+00:00"), NOW) == "—"


def test_to_argentina_moves_utc_three_hours_back():
    local = page.to_argentina(datetime(2026, 9, 14, 10, 2, tzinfo=timezone.utc))
    assert (local.hour, local.minute) == (7, 2)
    assert local.utcoffset() == timedelta(hours=-3)


def test_naive_timestamps_are_read_as_utc():
    local = page.to_argentina(datetime(2026, 9, 14, 2, 30))
    assert (local.date(), local.hour) == (date(2026, 9, 13), 23)


def test_missing_time_zone_data_falls_back_to_fixed_utc_minus_three(monkeypatch):
    def missing_zone(name):
        raise ZoneInfoNotFoundError(name)

    monkeypatch.setattr(page, "ZoneInfo", missing_zone)
    local = page.to_argentina(datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc))
    assert (local.hour, local.utcoffset()) == (9, timedelta(hours=-3))


def test_format_moment_shows_clock_today_yesterday_and_date_before():
    assert page.format_moment(datetime(2026, 9, 14, 10, 2, tzinfo=timezone.utc), NOW) == "07:02"
    # 02:03 UTC on the 14th is still the 13th in Buenos Aires.
    assert page.format_moment(datetime(2026, 9, 14, 2, 3, tzinfo=timezone.utc), NOW) == "ayer 23:03"
    assert page.format_moment(datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc), NOW) == "12 sep 07:00"
    assert page.format_moment(None, NOW) == "—"


def test_format_moment_in_english(monkeypatch):
    monkeypatch.setattr(i18n, "current_lang", lambda: "en")
    assert page.format_moment(datetime(2026, 9, 14, 2, 3, tzinfo=timezone.utc), NOW) == "yesterday 23:03"
    assert page.format_moment(datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc), NOW) == "Sep 12 07:00"


def test_window_text_counts_both_ends_of_the_period():
    assert page.window_text(date(2026, 8, 31), date(2026, 9, 13)) == "31 ago → 13 sep · 14 días"
    assert page.window_text(date(2026, 9, 13), date(2026, 9, 13)) == "13 sep → 13 sep · 1 día"
    assert page.window_text(None, date(2026, 9, 13)) == ""


@pytest.mark.parametrize("status, attempts, expected", [
    ("pending", 0, 0), ("running", 0, 1), ("completed", 0, 1), ("completed", 2, 3),
    ("retrying", 3, 3), ("failed", 8, 8), ("cancelled", 1, 1),
])
def test_attempts_shown_counts_the_attempt_in_progress(status, attempts, expected):
    assert page.attempts_shown(status, attempts) == expected


def test_format_count_groups_thousands_per_language(monkeypatch):
    assert page.format_count(186240) == "186.240"
    monkeypatch.setattr(i18n, "current_lang", lambda: "en")
    assert page.format_count(186240) == "186,240"


@pytest.mark.parametrize("status, lease_expires_at, expected", [
    ("pending", None, True),
    ("retrying", None, True),
    ("running", "2026-09-14T15:10:00+00:00", True),
    ("running", None, True),
    ("running", "2026-09-14T15:40:00+00:00", False),
    ("failed", None, False),
    ("completed", None, False),
    ("cancelled", None, False),
])
def test_only_queued_or_abandoned_running_jobs_can_be_cancelled(status, lease_expires_at, expected):
    job = _job(status=status, phase="waiting" if status == "running" else "", lease_expires_at=lease_expires_at)
    assert page.is_cancellable(job, NOW) is expected


def test_hint_key_maps_known_error_classes_and_falls_back():
    assert page.hint_key("NeedsReauth") == "request_log.hint.needs_reauth"
    assert page.hint_key("ReadTimeout") == "request_log.hint.network"
    assert page.hint_key("deadline") == "request_log.hint.deadline"
    assert page.hint_key("SomethingNew") == "request_log.hint.default"
    assert page.hint_key("") == "request_log.hint.default"


def test_every_hint_the_page_can_pick_has_both_translations():
    for error_class in (*page._HINT_SUFFIXES, "unknown"):
        key = page.hint_key(error_class)
        assert key in i18n._ES and key in i18n._EN, key


def test_verdict_is_never_all_clear_when_the_alerts_could_not_be_read():
    title = page.verdict_title(0, 0, read_ok=False)
    assert title != i18n.t("request_log.verdict.all_clear")
    assert title == i18n.t("request_log.verdict.read_failed")


@pytest.mark.parametrize("errors, warnings, expected", [
    (0, 0, "Nada requiere atención."),
    (1, 0, "1 problema requiere atención."),
    (3, 0, "3 problemas requieren atención."),
    (0, 2, "2 avisos para revisar."),
    (1, 2, "1 problema y 2 avisos para revisar."),
])
def test_verdict_counts_problems_and_warnings(errors, warnings, expected):
    assert page.verdict_title(errors, warnings, read_ok=True) == expected


def test_summary_line_lists_the_day_and_the_worker_heartbeat():
    counts = {"completed": 41, "running": 2, "pending": 1, "failed": 1}
    line = page.summary_line(counts, NOW - timedelta(seconds=38), NOW)
    assert line == ("Últimas 24 h: 41 completadas · 3 en curso · 1 fallida · "
                    "el sincronizador respondió hace 38 s")


def test_summary_line_without_requests_or_heartbeat():
    assert page.summary_line({}, None, NOW) == (
        "Últimas 24 h: sin solicitudes · el sincronizador todavía no reportó actividad")


def test_list_filters_translates_the_choices_into_store_arguments():
    choice = page.FilterChoice(provider="amazon_ads", status="failed", account="demo-profile-1",
                               period="week", only_problems=True)
    assert page.list_filters(choice, NOW) == {
        "slugs": ("amazon_ads",), "statuses": ("failed",), "external_account_id": "demo-profile-1",
        "since": NOW - timedelta(days=7), "only_problems": True,
    }


def test_list_filters_with_everything_open_reads_the_full_history():
    choice = page.FilterChoice(provider="", status="", account="", period="all", only_problems=False)
    assert page.list_filters(choice, NOW) == {
        "slugs": (), "statuses": (), "external_account_id": "", "since": None, "only_problems": False,
    }


class _PagedStore:
    def __init__(self, job_ids: list[int]):
        self._job_ids = job_ids
        self.calls: list[dict] = []

    def list_recent(self, *, limit: int, before_id: int | None, **filters) -> list[SyncJob]:
        self.calls.append({"limit": limit, "before_id": before_id, **filters})
        newer_first = [job_id for job_id in self._job_ids if before_id is None or job_id < before_id]
        return [_job(id=job_id) for job_id in newer_first[:limit]]


def test_load_more_continues_from_the_last_id_of_the_previous_page():
    store = _PagedStore(list(range(10, 0, -1)))
    jobs, has_more = page.load_job_pages(store, {"slugs": ()}, pages=2, page_size=4)
    assert [job.id for job in jobs] == [10, 9, 8, 7, 6, 5, 4, 3]
    assert has_more is True
    assert [call["before_id"] for call in store.calls] == [None, 7]
    assert all(call["slugs"] == () for call in store.calls)


def test_pagination_stops_at_the_first_short_page():
    store = _PagedStore([5, 4, 3])
    jobs, has_more = page.load_job_pages(store, {}, pages=3, page_size=4)
    assert [job.id for job in jobs] == [5, 4, 3]
    assert has_more is False
    assert len(store.calls) == 1


def test_report_progress_counts_saved_chunks_and_their_rows_per_job():
    progress = page.report_progress([
        {"job_id": 7, "status": "saved", "row_count": 12000},
        {"job_id": 7, "status": "saved", "row_count": 310},
        {"job_id": 7, "status": "requested", "row_count": None},
        {"job_id": 8, "status": "to_request"},
    ])
    assert progress[7] == page.ReportProgress(saved=2, total=3, rows_saved=12310)
    assert progress[8] == page.ReportProgress(saved=0, total=1, rows_saved=0)


def test_request_title_names_trigger_and_kind():
    assert page.request_title(_job()) == "Diaria · Search terms"
    assert page.request_title(_job(trigger="backfill")) == "Primera carga · Search terms"
    assert page.request_title(_job(trigger="manual", requested_by="analista-demo")) == "Manual · analista-demo"
    assert page.request_title(_job(job_kind="portfolio_names")) == "Nombres de portfolio"
    assert page.request_title(_job(job_kind="ai_str_analysis")) == "Diaria · Análisis IA de search terms"


def test_request_subline_says_what_matters_for_each_state():
    retrying = _job(status="retrying", next_attempt_at="2026-09-14T15:30:00+00:00")
    assert page.request_subline(retrying, None, NOW) == "próximo intento 12:30"
    running = _job(status="running", phase="waiting")
    assert page.request_subline(running, page.ReportProgress(2, 5, 24310), NOW) == "2 de 5 reportes listos"
    portfolios = _job(job_kind="portfolio_names", status="completed", rows_written=14, window_start=None,
                      window_end=None)
    assert page.request_subline(portfolios, None, NOW) == "14 portfolios"
    assert page.request_subline(_job(status="failed"), None, NOW) == "31 ago → 13 sep · 14 días"


def test_the_campaign_grain_reads_like_its_siblings_in_the_log():
    assert page.request_title(_job(job_kind="sp_campaigns")) == "Diaria · Métricas de campañas"
    assert page.request_title(_job(job_kind="campaign_entities")) == "Campañas"
    entities = _job(job_kind="campaign_entities", status="completed", rows_written=276, window_start=None,
                    window_end=None)
    assert page.request_subline(entities, None, NOW) == "276 campañas"


def test_rows_of_an_open_job_come_from_its_saved_reports():
    running = _job(status="running", phase="waiting")
    assert page.rows_text(running, page.ReportProgress(2, 5, 24310)) == "24.310"
    assert page.rows_text(running, None) == "—"
    assert page.rows_text(_job(status="completed", rows_written=0), None) == "0"


def test_timeline_lists_creation_attempts_and_the_closing_error_once():
    job = _job(
        status="failed", attempts=2, max_attempts=2, finished_at="2026-09-14T14:42:00+00:00",
        error_class="ReportFailed", error_message="Amazon could not build report",
        attempt_log=[
            {"attempt": 1, "at": "2026-09-14T11:00:00+00:00", "error_class": "ReportTimedOut",
             "message": "report still PENDING"},
            {"attempt": 2, "at": "2026-09-14T14:42:00+00:00", "error_class": "ReportFailed",
             "message": "Amazon could not build report"},
        ],
    )
    entries = page.timeline(job)
    assert [entry.label for entry in entries] == ["Creada", "Intento 1", "Intento 2"]
    assert entries[0].text == "Programada, actualización diaria"
    assert entries[2].text == "ReportFailed · Amazon could not build report"
    assert entries[2].is_error


def test_timeline_adds_the_deadline_failure_the_attempt_log_never_saw():
    job = _job(status="failed", finished_at="2026-09-14T14:00:00+00:00", error_class="deadline",
               error_message="Venció el plazo antes de completarse.")
    entries = page.timeline(job)
    assert entries[-1].label == "Fallida"
    assert entries[-1].text == "deadline · Venció el plazo antes de completarse."


def test_timeline_of_a_completed_job_ends_with_the_rows_saved():
    job = _job(status="completed", rows_written=12480, finished_at="2026-09-14T10:10:00+00:00")
    assert page.timeline(job)[-1].text == "12.480 filas guardadas."


class _ActionStore:
    def __init__(self, retry_answer=None, cancel_answer=False, error: Exception | None = None):
        self._retry_answer = retry_answer
        self._cancel_answer = cancel_answer
        self._error = error
        self.calls: list[tuple] = []

    def retry(self, job_id: int, actor: str):
        self.calls.append(("retry", job_id, actor))
        if self._error:
            raise self._error
        return self._retry_answer

    def cancel(self, job_id: int, actor: str):
        self.calls.append(("cancel", job_id, actor))
        if self._error:
            raise self._error
        return self._cancel_answer


def test_retry_handler_refuses_a_non_admin_without_touching_the_store():
    store = _ActionStore(retry_answer=77)
    outcome = page.retry_request(store, 41, "analista-demo", role="usuario")
    assert not outcome.succeeded
    assert outcome.message == i18n.t("request_log.admin_only")
    assert store.calls == []


def test_retry_handler_reports_the_new_request():
    store = _ActionStore(retry_answer=77)
    outcome = page.retry_request(store, 41, "admin-demo", role="admin")
    assert outcome == page.ActionOutcome(True, "Se creó la solicitud #77 para reintentar la #41.")
    assert store.calls == [("retry", 41, "admin-demo")]


def test_retry_handler_explains_a_job_that_is_not_retryable():
    outcome = page.retry_request(_ActionStore(retry_answer=None), 41, "admin-demo", role="admin")
    assert not outcome.succeeded and "#41" in outcome.message


def test_retry_handler_turns_a_store_error_into_its_message():
    store = _ActionStore(error=StoreError("No se pudo reintentar la solicitud."))
    outcome = page.retry_request(store, 41, "admin-demo", role="admin")
    assert outcome == page.ActionOutcome(False, "No se pudo reintentar la solicitud.")


def test_cancel_handler_refuses_a_non_admin_and_reports_both_answers():
    refused_store = _ActionStore(cancel_answer=True)
    assert not page.cancel_request(refused_store, 41, "analista-demo", role="usuario").succeeded
    assert refused_store.calls == []
    assert page.cancel_request(_ActionStore(cancel_answer=True), 41, "admin-demo", "admin") == \
        page.ActionOutcome(True, "Solicitud #41 cancelada.")
    assert not page.cancel_request(_ActionStore(cancel_answer=False), 41, "admin-demo", "admin").succeeded


def test_accounts_action_points_at_a_real_destination():
    from core import navigation

    assert page.ACCOUNTS_PAGE in navigation.all_pages()


def _alert(severity: str) -> SyncAlert:
    return SyncAlert(kind="failed_today", severity=severity, integration_slug="amazon_ads",
                     subject="cliente-demo", marketplaces="MX", detail="", since=NOW)


def test_sync_alert_counts_is_zero_without_a_database(monkeypatch):
    monkeypatch.setattr(notice, "_rest_credentials", lambda: None)
    notice.sync_alert_counts.clear()
    assert notice.sync_alert_counts() == (0, 0)


def test_sync_alert_counts_never_raises(monkeypatch):
    def broken_read(rest, now):
        raise RuntimeError("database down")

    monkeypatch.setattr(notice, "_rest_credentials", lambda: ("http://rest.invalid", "demo-key"))
    monkeypatch.setattr(notice, "load_alerts", broken_read)
    notice.sync_alert_counts.clear()
    assert notice.sync_alert_counts() == (0, 0)


def test_sync_alert_counts_splits_errors_and_warnings(monkeypatch):
    monkeypatch.setattr(notice, "_rest_credentials", lambda: ("http://rest.invalid", "demo-key"))
    monkeypatch.setattr(notice, "load_alerts",
                        lambda rest, now: ([_alert(ERROR), _alert(WARNING), _alert(WARNING)], True))
    notice.sync_alert_counts.clear()
    assert notice.sync_alert_counts() == (1, 2)
    notice.sync_alert_counts.clear()


def _non_admin_script():
    from modules.pages import request_log as page

    def no_database_expected():
        raise AssertionError("a non-admin render must not open the database")

    original = page._open_rest
    page._open_rest = no_database_expected
    try:
        page.render(username="analista-demo", role="usuario")
    finally:
        page._open_rest = original


def _admin_script():
    from datetime import datetime, timedelta, timezone

    from modules.pages import request_log as page

    now = datetime.now(timezone.utc)
    base = {
        "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "scheduled_daily",
        "external_account_id": "demo-profile-1", "cliente": "cliente-demo", "account_name": "Demo Seller",
        "marketplace": "MX", "region": "NA", "phase": "", "max_attempts": 8, "attempt_log": [],
        "window_start": "2026-08-31", "window_end": "2026-09-13", "deadline_at": (now + timedelta(hours=6)).isoformat(),
        "created_at": (now - timedelta(hours=5)).isoformat(), "started_at": (now - timedelta(hours=5)).isoformat(),
    }
    failed = {**base, "id": 41, "status": "failed", "attempts": 8, "error_class": "ReportFailed",
              "error_message": "Amazon could not build report", "finished_at": (now - timedelta(hours=1)).isoformat()}
    completed = {**base, "id": 40, "status": "completed", "attempts": 0, "rows_written": 12480,
                 "external_account_id": "demo-profile-2", "cliente": "otra-demo",
                 "finished_at": (now - timedelta(hours=4)).isoformat()}

    class FakeRest:
        def select(self, table, params):
            if table == "integration_sync_jobs":
                if params.get("status") == "in.(failed,completed)":
                    return [failed]
                if params.get("status") == "eq.running":
                    return []
                if params.get("select") == "status":
                    return [{"status": "failed"}, {"status": "completed"}]
                return [failed, completed]
            if table == "integration_worker_heartbeats":
                return [{"worker_name": "amazon_ads", "last_tick_at": now.isoformat()}]
            return []

        def rpc(self, name, args, **kwargs):
            return 77 if name == "retry_sync_job" else None

    original = page._open_rest
    page._open_rest = FakeRest
    try:
        page.render(username="admin-demo", role="admin")
    finally:
        page._open_rest = original


def _markdown_text(app) -> str:
    return " ".join(str(block.value) for block in app.markdown)


def test_non_admin_sees_only_the_admin_notice():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_function(_non_admin_script, default_timeout=60)
    app.run()
    assert not app.exception
    assert [block.value for block in app.info] == [i18n.t("request_log.admin_only")]
    assert len(app.button) == 0


def test_admin_page_renders_the_failure_and_retries_it():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_function(_admin_script, default_timeout=60)
    app.run()
    assert not app.exception
    text = _markdown_text(app)
    assert "1 problema requiere atención." in text
    assert "Falló hoy" in text and "Fallida" in text and "12.480" in text
    assert {button.key for button in app.button} >= {"rl_act_retry_41", "rl_view_41", "rl_view_40"}

    app.button(key="rl_act_retry_41").click().run()
    assert not app.exception
    assert [block.value for block in app.success] == ["Se creó la solicitud #77 para reintentar la #41."]


def _first_load_script():
    from datetime import datetime, timedelta, timezone

    from modules.pages import request_log as page

    now = datetime.now(timezone.utc)
    backfill = {
        "id": 52, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "backfill",
        "external_account_id": "demo-profile-3", "cliente": "nueva-demo", "account_name": "Nueva Demo",
        "marketplace": "US", "region": "NA", "status": "failed", "phase": "", "attempts": 1, "max_attempts": 6,
        "attempt_log": [], "error_class": "AdsAccessDenied", "error_message": "HTTP 403",
        "window_start": "2026-07-11", "window_end": "2026-09-13", "deadline_at": (now - timedelta(days=2)).isoformat(),
        "created_at": (now - timedelta(days=3)).isoformat(), "finished_at": (now - timedelta(days=3)).isoformat(),
    }
    profile = {"profile_id": "demo-profile-3", "cliente": "nueva-demo", "country_code": "US", "region": "NA",
               "timezone": "America/Los_Angeles", "status": "active", "backfill_done_at": None}

    class FakeRest:
        def select(self, table, params):
            if table == "integration_sync_jobs":
                if "trigger" in params:
                    return [backfill]
                if params.get("status") in ("in.(failed,completed)", "eq.running") or params.get("select") == "status":
                    return []
                return [backfill]
            if table == "ads_profile_sync":
                return [profile]
            if table == "integration_worker_heartbeats":
                return [{"worker_name": "amazon_ads", "last_tick_at": now.isoformat()}]
            return []

        def rpc(self, name, args, **kwargs):
            return 78 if name == "retry_sync_job" else None

    original = page._open_rest
    page._open_rest = FakeRest
    try:
        page.render(username="admin-demo", role="admin")
    finally:
        page._open_rest = original


def test_failed_first_load_is_an_alert_with_a_retry_days_after_it_failed():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_function(_first_load_script, default_timeout=60)
    app.run()
    assert not app.exception
    text = _markdown_text(app)
    assert "Primera carga fallida" in text
    assert "La carga inicial no se completó: AdsAccessDenied." in text

    app.button(key="rl_act_retry_52").click().run()
    assert not app.exception
    assert [block.value for block in app.success] == ["Se creó la solicitud #78 para reintentar la #52."]


def _abandoned_script():
    from datetime import datetime, timedelta, timezone

    from modules.pages import request_log as page

    now = datetime.now(timezone.utc)
    abandoned = {
        "id": 61, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "backfill",
        "external_account_id": "demo-profile-4", "cliente": "trabada-demo", "marketplace": "MX", "region": "NA",
        "status": "running", "phase": "waiting", "attempts": 0, "max_attempts": 6, "attempt_log": [],
        "lease_holder": "worker-a", "lease_expires_at": (now - timedelta(hours=2)).isoformat(),
        "window_start": "2026-07-11", "window_end": "2026-09-13", "deadline_at": (now + timedelta(hours=6)).isoformat(),
        "created_at": (now - timedelta(hours=3)).isoformat(), "started_at": (now - timedelta(hours=3)).isoformat(),
    }
    class FakeRest:
        def select(self, table, params):
            if table == "integration_sync_jobs":
                if params.get("status") in ("in.(failed,completed)", "eq.running") or params.get("select") == "status":
                    return []
                return [abandoned]
            if table == "integration_worker_heartbeats":
                return [{"worker_name": "amazon_ads", "last_tick_at": now.isoformat()}]
            return []

    original = page._open_rest
    page._open_rest = FakeRest
    try:
        page.render(username="admin-demo", role="admin")
    finally:
        page._open_rest = original


def test_detail_of_a_running_job_whose_lease_lapsed_offers_cancel():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_function(_abandoned_script, default_timeout=60)
    app.run()
    app.button(key="rl_view_61").click().run()
    assert not app.exception
    assert i18n.t("request_log.detail.cancel_abandoned_caption") in [block.value for block in app.caption]
    assert app.button(key="rl_detail_cancel_61").label == i18n.t("request_log.btn.cancel_job")


def _unmigrated_script():
    import requests

    from modules.pages import request_log as page

    class MissingTablesRest:
        def select(self, table, params):
            response = requests.Response()
            response.status_code = 404
            raise requests.HTTPError(f"404 for {table}", response=response)

    original = page._open_rest
    page._open_rest = MissingTablesRest
    try:
        page.render(username="admin-demo", role="admin")
    finally:
        page._open_rest = original


def test_admin_page_before_the_migration_says_it_cannot_read_instead_of_all_clear():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_function(_unmigrated_script, default_timeout=60)
    app.run()
    assert not app.exception
    text = _markdown_text(app)
    assert i18n.t("request_log.verdict.read_failed") in text
    assert i18n.t("request_log.verdict.all_clear") not in text
    assert i18n.t("request_log.alerts.read_failed") in text
    assert "0 alertas" not in text
    assert [block.value for block in app.warning] == [i18n.t("request_log.requests.read_failed")]

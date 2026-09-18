"""Campaign source picker (modules/pages/campaign_source.py) and its first consumer, M6.

Pure helpers are tested directly with hand-derived expectations; the Streamlit flow runs in AppTest over
an in-file fake PostgREST client (no network: `_open_rest` is replaced before every script run).
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
import requests
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import modules.pages.campaign_source as campaign_picker
import modules.pages.search_term_source as search_term_source
from core.amazon_ads.report_provider import ProfileOption
from core.integrations.sync_jobs import SyncJob

_PROFILE_TZ = "America/Los_Angeles"
RPC_HEADER = ["campaign_id", "name", "state", "targeting_type", "start_date", "budget_amount", "budget_type",
              "bidding_strategy", "portfolio_id", "portfolio_name", "impressions", "clicks", "cost",
              "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "currency_code"]
# 22:10 in Buenos Aires on 17 Sep, where the pill dates syncs; 18:10 in the profile's Los Angeles.
NOW = datetime(2026, 9, 18, 1, 10, tzinfo=timezone.utc)


def _profile_today() -> date:
    """The picker dates data in the profile's own zone, so the runner's clock must not name the days."""
    return datetime.now(timezone.utc).astimezone(search_term_source.profile_timezone(_PROFILE_TZ, "")).date()


def _synced_today() -> datetime:
    """A sync dated inside today's display day, whatever hour the suite runs at."""
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(search_term_source.DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0,
                                                                           microsecond=0)
    return max(now - timedelta(hours=1), midnight.astimezone(timezone.utc))


def _profile_row(**overrides) -> dict:
    row = {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids MX",
           "country_code": "MX", "currency_code": "MXN", "account_type": "seller", "timezone": _PROFILE_TZ,
           "status": "active", "data_from": None, "data_through": None, "refreshed_on": None,
           "last_success_at": None, "last_error": ""}
    row.update(overrides)
    return row


def _job_row(job_id=41, *, status="completed", window_end=None, local_day=None, finished_at=None,
             created_at=None) -> dict:
    window_end = window_end or _profile_today() - timedelta(days=1)
    return {"id": job_id, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns", "trigger": "scheduled_daily",
            "external_account_id": "111", "status": status, "phase": "", "attempts": 0, "max_attempts": 6,
            "window_start": (window_end - timedelta(days=64)).isoformat(), "window_end": window_end.isoformat(),
            "local_day": (local_day or _profile_today()).isoformat(),
            "finished_at": (finished_at or _synced_today()).isoformat() if status == "completed" else None,
            "created_at": (created_at or _synced_today()).isoformat()}


def _campaign(campaign_id, name, *, state="ENABLED", impressions=0, clicks=0, cost=0.0, purchases=0,
              sales=0.0) -> dict:
    return {"campaign_id": campaign_id, "name": name, "state": state, "targeting_type": "MANUAL",
            "start_date": "2026-03-21", "budget_amount": "15.0", "budget_type": "DAILY",
            "bidding_strategy": "MANUAL", "portfolio_id": "", "portfolio_name": "",
            "impressions": str(impressions), "clicks": str(clicks), "cost": str(cost),
            "purchases_7d": str(purchases), "sales_7d": str(sales), "purchases_14d": str(purchases),
            "sales_14d": str(sales), "currency_code": "MXN"}


def _csv(rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RPC_HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class _FakeRest:
    """In-memory PostgREST: the profile table, the campaign sync jobs and `campaigns_between`."""

    def __init__(self, profile_rows, campaign_rows=(), jobs=(), jobs_down=False):
        self.profile_rows = list(profile_rows)
        self.campaign_rows = list(campaign_rows)
        self.jobs = list(jobs)
        self.jobs_down = jobs_down
        self.campaign_reads: list[dict] = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [dict(row) for row in self.profile_rows]
        if table == "integration_sync_jobs":
            if self.jobs_down:
                raise requests.ConnectionError("pool timeout")
            jobs = [job for job in self.jobs if params["job_kind"] == f"eq.{job['job_kind']}"]
            if params.get("status") == "eq.completed":
                jobs = sorted((job for job in jobs if job["status"] == "completed"),
                              key=lambda job: job["finished_at"], reverse=True)
            else:
                jobs = sorted(jobs, key=lambda job: job["created_at"], reverse=True)
            return [dict(job) for job in jobs[:1]]
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, *, timeout_s=8):
        assert name == "campaigns_between"
        self.campaign_reads.append(args)
        return _csv(self.campaign_rows)


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


_PICKER_SCRIPT = """
import streamlit as st
from modules.pages.campaign_source import render_campaign_source
st.cache_data.clear()
result = render_campaign_source("bulk")
st.session_state["test_result"] = None if result is None else (
    len(result.frame), result.currency_code, list(result.frame["Campaign ID"]))
"""

_M6_SCRIPT = """
import streamlit as st
st.cache_data.clear()
from modules.pages.bulk_campanas import render
render()
"""

# The header as its fragment runs it: the first run stands for a poll started while the job was open.
_HEADER_SCRIPT = """
import streamlit as st
from modules.pages.campaign_source import _render_header
st.cache_data.clear()
runs = st.session_state["header_runs"] = st.session_state.get("header_runs", 0) + 1
_render_header(st.session_state["test_option"], False, runs == 1)
"""


def _app(monkeypatch, fake, script=_PICKER_SCRIPT) -> AppTest:
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: fake)
    return AppTest.from_string(script, default_timeout=30)


def _text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.markdown]
    parts += [str(element.value) for element in app.info] + [str(element.value) for element in app.error]
    return " ".join(parts)


def _option(**overrides) -> ProfileOption:
    return ProfileOption.from_row(_profile_row(**overrides))


def _job(**overrides) -> SyncJob:
    row = _job_row(window_end=date(2026, 9, 16), local_day=date(2026, 9, 17),
                   finished_at=datetime(2026, 9, 18, 0, 51, tzinfo=timezone.utc),
                   created_at=datetime(2026, 9, 18, 0, 43, tzinfo=timezone.utc))
    row.update(overrides)
    return SyncJob.from_row(row)


class TestCampaignView:
    def test_the_last_good_job_is_what_the_campaign_data_covers_and_when_it_arrived(self):
        view = campaign_picker.campaign_view(_option(), _job())

        assert (view.data_from, view.data_through) == (date(2026, 7, 14), date(2026, 9, 16))
        assert view.refreshed_on == date(2026, 9, 17)
        assert view.last_success_at == datetime(2026, 9, 18, 0, 51, tzinfo=timezone.utc)

    def test_the_search_term_freshness_of_the_profile_never_leaks_into_the_campaign_view(self):
        option = _option(data_through="2026-09-16", last_success_at="2026-09-17T12:24:00+00:00")

        view = campaign_picker.campaign_view(option, None)

        assert (view.data_from, view.data_through, view.refreshed_on, view.last_success_at) == (None,) * 4


class TestCampaignPill:
    def test_before_any_campaign_job_there_is_no_load_to_announce(self):
        assert campaign_picker.campaign_pill(campaign_picker.campaign_view(_option(), None), None, NOW) == (
            "idle", "Sin datos todavía")

    def test_a_first_load_in_course_says_so(self):
        view = campaign_picker.campaign_view(_option(), None)

        assert campaign_picker.campaign_pill(view, _job(status="running"), NOW) == ("idle", "Primera carga en curso")

    def test_a_first_load_that_failed_says_so(self):
        view = campaign_picker.campaign_view(_option(), None)

        assert campaign_picker.campaign_pill(view, _job(status="failed"), NOW) == ("err", "La primera carga falló")

    def test_a_sync_finished_today_names_the_day_and_the_hour(self):
        completed = _job()

        view = campaign_picker.campaign_view(_option(), completed)

        # 00:51 UTC on the 18th is 21:51 on the 17th in Buenos Aires, where the pill dates syncs.
        assert campaign_picker.campaign_pill(view, completed, NOW) == ("ok", "Al día · actualizado hoy 21:51")

    def test_a_new_sync_in_course_names_the_hour_it_was_asked_for(self):
        view = campaign_picker.campaign_view(_option(), _job())
        running = _job(id=42, status="running", created_at="2026-09-18T01:00:00+00:00")

        assert campaign_picker.campaign_pill(view, running, NOW) == ("idle", "Actualizando · pedido a las 22:00")

    def test_a_profile_amazon_stopped_authorizing_says_since_when(self):
        completed = _job()

        view = campaign_picker.campaign_view(_option(status="needs_reauth"), completed)

        assert campaign_picker.campaign_pill(view, completed, NOW) == ("err", "Sin actualizar desde hoy 21:51")


class TestReadCampaignFile:
    def test_a_csv_is_read_as_is(self):
        frame = campaign_picker.read_campaign_file(b"Campaign name,State,Total cost\nA,ENABLED,1.5\n", "camps.csv")

        assert list(frame.columns) == ["Campaign name", "State", "Total cost"] and frame.loc[0, "Total cost"] == 1.5

    def test_an_xlsx_is_read_as_is(self):
        buffer = io.BytesIO()
        pd.DataFrame({"Campaign name": ["A"], "State": ["ENABLED"]}).to_excel(buffer, index=False)

        frame = campaign_picker.read_campaign_file(buffer.getvalue(), "bulk.xlsx")

        assert list(frame["Campaign name"]) == ["A"]


class TestPickerApp:
    def test_without_connected_accounts_it_is_the_old_uploader_plus_the_hint(self, monkeypatch):
        app = _app(monkeypatch, None)
        app.run()

        assert not app.exception
        assert app.session_state["test_result"] is None
        assert [caption.value for caption in app.caption] == [search_term_source.NO_CONNECTION_HINT]
        assert app.get("file_uploader")[0].label == campaign_picker.UPLOAD_LABEL

    def test_a_synced_account_returns_its_campaigns_with_the_day_and_hour_of_the_sync(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_campaign("1", "Alpha"), _campaign("2", "Beta")], jobs=[_job_row()])
        app = _app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert app.session_state["test_result"] == (2, "MXN", ["1", "2"])
        page = _text(app)
        assert "Datos de Amazon Ads" in page and "Al día · actualizado hoy" in page
        assert "2 campañas" in page and "Datos hasta ayer (hora del perfil)" in page

    def test_the_default_period_reads_the_last_seven_synced_days(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_campaign("1", "Alpha")], jobs=[_job_row()])
        app = _app(monkeypatch, fake)
        app.run()

        yesterday = _profile_today() - timedelta(days=1)
        assert fake.campaign_reads == [{"p_profile_id": "111", "p_from": (yesterday - timedelta(days=6)).isoformat(),
                                        "p_to": yesterday.isoformat()}]

    def test_an_account_the_campaign_sync_never_reached_says_so_and_offers_the_file(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_campaign("1", "Alpha")])
        app = _app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert app.session_state["test_result"] is None
        assert campaign_picker.NO_CAMPAIGN_DATA_MESSAGE in _text(app)
        assert "Sin datos todavía" in _text(app)
        assert "Subir archivo manualmente" in [button.label for button in app.button]
        assert fake.campaign_reads == []

    def test_a_first_load_in_course_waits_instead_of_reading(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_campaign("1", "Alpha")], jobs=[_job_row(status="running")])
        app = _app(monkeypatch, fake)
        app.run()

        assert app.session_state["test_result"] is None
        assert campaign_picker.FIRST_LOAD_MESSAGE in _text(app) and "Primera carga en curso" in _text(app)
        assert fake.campaign_reads == []

    def test_a_first_load_that_failed_is_an_error_with_a_way_out(self, monkeypatch):
        fake = _FakeRest([_profile_row()], jobs=[_job_row(status="failed")])
        app = _app(monkeypatch, fake)
        app.run()

        assert app.session_state["test_result"] is None
        assert campaign_picker.FIRST_LOAD_FAILED_MESSAGE in _text(app)
        assert "Subir archivo manualmente" in [button.label for button in app.button]

    def test_a_sync_state_that_cannot_be_read_is_an_error_with_a_way_out(self, monkeypatch):
        fake = _FakeRest([_profile_row()], jobs_down=True)
        app = _app(monkeypatch, fake)
        app.run()

        assert not app.exception
        assert app.session_state["test_result"] is None
        assert search_term_source.ASK_AN_ADMIN in _text(app)
        assert "Subir archivo manualmente" in [button.label for button in app.button]

    def test_an_account_with_only_archived_campaigns_is_an_empty_state_not_an_empty_table(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_campaign("1", "Old", state="ARCHIVED")], jobs=[_job_row()])
        app = _app(monkeypatch, fake)
        app.run()

        assert app.session_state["test_result"] is None
        assert campaign_picker.NO_CAMPAIGNS_MESSAGE in _text(app)

    def test_manual_mode_shows_the_uploader_and_the_way_back(self, monkeypatch):
        fake = _FakeRest([_profile_row()], [_campaign("1", "Alpha")], jobs=[_job_row()])
        app = _app(monkeypatch, fake)
        app.session_state["bulk_src_manual"] = True
        app.run()

        assert not app.exception
        assert app.session_state["test_result"] is None
        assert "Volver a datos de Amazon Ads" in [button.label for button in app.button]
        assert app.get("file_uploader")[0].label == campaign_picker.UPLOAD_LABEL
        assert fake.campaign_reads == []


class TestHeaderPolling:
    def _run(self, monkeypatch, fake) -> AppTest:
        app = _app(monkeypatch, fake, script=_HEADER_SCRIPT)
        app.session_state["test_option"] = _option()
        app.run()
        assert not app.exception
        return app

    def test_a_poll_of_a_job_still_open_redraws_only_the_pill(self, monkeypatch):
        app = self._run(monkeypatch, _FakeRest([_profile_row()], jobs=[_job_row(status="running")]))

        assert app.session_state["header_runs"] == 1
        assert "Primera carga en curso" in _text(app)

    def test_when_the_polled_job_closes_the_whole_picker_redraws(self, monkeypatch):
        app = self._run(monkeypatch, _FakeRest([_profile_row()], jobs=[_job_row()]))

        assert app.session_state["header_runs"] == 2
        assert "Al día · actualizado hoy" in _text(app)

    def test_a_poll_that_cannot_read_the_jobs_says_so_instead_of_failing(self, monkeypatch):
        app = self._run(monkeypatch, _FakeRest([_profile_row()], jobs_down=True))

        assert app.session_state["header_runs"] == 1
        assert "No se pudo leer" in _text(app)


class TestBulkCampanasOnApiData:
    def _run(self, monkeypatch) -> AppTest:
        campaigns = [
            _campaign("1", "Ghost"),
            _campaign("2", "Bleeder", impressions=900, clicks=30, cost=30.0),
            _campaign("3", "Winner", impressions=2000, clicks=40, cost=10.0, purchases=4, sales=100.0),
            _campaign("4", "Paused bleeder", state="PAUSED", impressions=500, clicks=20, cost=50.0),
        ]
        app = _app(monkeypatch, _FakeRest([_profile_row()], campaigns, jobs=[_job_row()]), script=_M6_SCRIPT)
        app.run()
        assert not app.exception
        return app

    def test_the_analyzer_finds_the_ghost_the_bleeder_and_the_winner(self, monkeypatch):
        metrics = {metric.label: metric.value for metric in self._run(monkeypatch).metric}

        assert (metrics["👻 Fantasmas"], metrics["🔴 Pausar"], metrics["✅ Escalar"]) == ("1", "1", "1")
        # Only enabled campaigns are analyzed: the paused one stays out.
        assert metrics["Campañas analizadas"] == "3"

    def test_amounts_read_in_the_account_currency_instead_of_a_hardcoded_dollar(self, monkeypatch):
        app = self._run(monkeypatch)
        metrics = {metric.label: metric.value for metric in app.metric}

        assert (metrics["Total Spend"], metrics["Total Sales"]) == ("MX$40.00", "MX$100.00")
        assert metrics["💰 Spend recuperable"] == "MX$30.00"
        assert "Spend mínimo para PAUSAR (MX$)" in [number.label for number in app.number_input]

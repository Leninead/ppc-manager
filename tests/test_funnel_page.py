"""Análisis de Funnel page over an in-memory PostgREST: one account choice feeds the search terms and the campaigns.

No network: `_open_rest` is replaced before every script run, and the AI tab runs with AI disabled.
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import modules.pages.search_term_source as search_term_source
from core.chat.screen_selection import FROM_HAND_UPLOAD, HAND_UPLOAD_NOTE, OLDER_DATA_NOTE
from core.search_term.frame import SOURCE_API, SOURCE_FILE, SearchTermSource
from modules.pages import analisis_funnel

_PROFILE_TZ = "America/Los_Angeles"
SEARCH_TERM_COLUMNS = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting",
                       "search_term", "campaign_name", "campaign_status", "ad_group_name", "keyword_text",
                       "ad_keyword_status", "portfolio_id", "portfolio_name", "currency_code", "impressions", "clicks",
                       "purchases_7d", "units_7d", "purchases_14d", "units_14d", "cost", "sales_7d", "sales_14d"]
CAMPAIGN_COLUMNS = ["campaign_id", "name", "state", "targeting_type", "start_date", "budget_amount", "budget_type",
                    "bidding_strategy", "portfolio_id", "portfolio_name", "impressions", "clicks", "cost",
                    "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "currency_code"]


def _profile_today() -> date:
    return datetime.now(timezone.utc).astimezone(search_term_source.profile_timezone(_PROFILE_TZ, "")).date()


def _synced_today() -> datetime:
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(search_term_source.DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(now - timedelta(hours=1), midnight.astimezone(timezone.utc))


def _profile_row() -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids MX",
            "country_code": "MX", "currency_code": "MXN", "account_type": "seller", "timezone": _PROFILE_TZ,
            "status": "active", "data_from": (yesterday - timedelta(days=64)).isoformat(),
            "data_through": yesterday.isoformat(), "refreshed_on": _profile_today().isoformat(),
            "last_success_at": _synced_today().isoformat(), "last_error": ""}


def _job_row(job_id, kind) -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"id": job_id, "integration_slug": "amazon_ads", "job_kind": kind, "trigger": "scheduled_daily",
            "external_account_id": "111", "status": "completed", "phase": "", "attempts": 0, "max_attempts": 6,
            "window_start": (yesterday - timedelta(days=64)).isoformat(), "window_end": yesterday.isoformat(),
            "local_day": _profile_today().isoformat(), "finished_at": _synced_today().isoformat(),
            "created_at": _synced_today().isoformat()}


def _term(search_term, campaign_id, campaign_name, *, clicks, orders, cost, sales):
    return {"campaign_id": campaign_id, "ad_group_id": "4001", "keyword_type": "EXACT", "keyword_id": "5001",
            "match_type": "EXACT", "targeting": search_term, "search_term": search_term,
            "campaign_name": campaign_name, "campaign_status": "ENABLED", "ad_group_name": "AG",
            "keyword_text": search_term, "ad_keyword_status": "ENABLED", "portfolio_id": "", "portfolio_name": "",
            "currency_code": "MXN", "impressions": 500, "clicks": clicks, "purchases_7d": orders, "units_7d": orders,
            "purchases_14d": orders, "units_14d": orders, "cost": cost, "sales_7d": sales, "sales_14d": sales}


def _campaign(campaign_id, name, *, state="ENABLED", impressions=0, clicks=0, cost=0.0):
    return {"campaign_id": campaign_id, "name": name, "state": state, "targeting_type": "MANUAL",
            "start_date": "2026-03-21", "budget_amount": "15.0", "budget_type": "DAILY", "bidding_strategy": "MANUAL",
            "portfolio_id": "", "portfolio_name": "", "impressions": str(impressions), "clicks": str(clicks),
            "cost": str(cost), "purchases_7d": "0", "sales_7d": "0", "purchases_14d": "0", "sales_14d": "0",
            "currency_code": "MXN"}


SEARCH_TERMS = [
    # The report still carries the name campaign 3001 had before the AM renamed it.
    _term("luna pajamas", "3001", "Luna - B0CYLMJJJC - SP - KW - EXACT - Viejo", clicks=40, orders=9, cost=30.0,
          sales=450.0),
    _term("sleep sack", "3002", "Luna - B0CYLMJJJC - SP - KW - BROAD - Pausada", clicks=12, orders=0, cost=18.0,
          sales=0.0),
]
CAMPAIGNS = [
    _campaign("3001", "Luna - B0CYLMJJJC - SP - KW - EXACT - Brand", impressions=900, clicks=40, cost=30.0),
    _campaign("3002", "Luna - B0CYLMJJJC - SP - KW - BROAD - Pausada", state="PAUSED"),
    _campaign("3003", "Luna - B0CYLMJJJC - SP - KW - PHRASE - Fantasma"),
]


def _csv(columns, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class _FakeRest:
    """The profile table, the sync jobs of both reports, and the two reads the page makes."""

    def __init__(self, *, campaign_jobs=True):
        self.jobs = [_job_row(7, "sp_search_terms")] + ([_job_row(8, "sp_campaigns")] if campaign_jobs else [])
        self.reads: list[tuple[str, dict]] = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [_profile_row()]
        if table == "integration_sync_jobs":
            kind = params.get("job_kind", "eq.sp_search_terms").removeprefix("eq.")
            return [dict(job) for job in self.jobs if job["job_kind"] == kind][:1]
        if table in ("ads_report_requests", "ai_analysis_settings", "ai_analyses"):
            return []
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.reads.append((name, args))
        if name == "search_terms_between":
            return _csv(SEARCH_TERM_COLUMNS, SEARCH_TERMS)
        assert name == "campaigns_between"
        return _csv(CAMPAIGN_COLUMNS, CAMPAIGNS)


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


_PAGE_SCRIPT = """
import streamlit as st
st.cache_data.clear()
st.session_state.setdefault("selected_page", "🔻 Análisis de Funnel")
from modules.pages.analisis_funnel import render
render()
"""


def _run(monkeypatch, fake) -> AppTest:
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: fake)
    monkeypatch.setattr("ai.config.AI_ENABLED", False)
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def _text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.markdown] + [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.info] + [str(element.value) for element in app.success]
    return " ".join(parts)


def test_one_account_choice_reads_the_search_terms_and_the_campaigns_of_the_same_period(monkeypatch):
    fake = _FakeRest()

    app = _run(monkeypatch, fake)

    reads = dict(fake.reads)
    assert (reads["campaigns_between"]["p_from"], reads["campaigns_between"]["p_to"]) == (
        reads["search_terms_between"]["p_from"], reads["search_terms_between"]["p_to"])
    assert reads["campaigns_between"]["p_profile_id"] == "111"
    assert [tab.label for tab in app.tabs] == ["🔗 Cobertura", "📦 Campañas sugeridas", "🌾 Harvesting",
                                               "🤖 Análisis IA"]
    assert "Campañas de la cuenta" in _text(app)


def test_a_renamed_campaign_keeps_its_terms_and_the_idle_one_is_listed(monkeypatch):
    app = _run(monkeypatch, _FakeRest())

    text = _text(app)
    assert analisis_funnel.MATCHED_BY_ID_NOTE in text
    coverage_tab = app.tabs[0]
    gaps, idle = coverage_tab.dataframe[2].value, coverage_tab.dataframe[3].value
    assert list(idle["Campaign name"]) == ["Luna - B0CYLMJJJC - SP - KW - PHRASE - Fantasma"]
    assert list(gaps["Customer Search Term"]) == ["sleep sack"]
    assert list(gaps["Estado de la campaña"]) == ["PAUSED"]
    assert "_campaign_id" not in gaps.columns


def test_the_chat_learns_the_account_the_days_and_the_values_on_screen(monkeypatch):
    app = _run(monkeypatch, _FakeRest())

    selection = app.session_state["app_chat_selections"]["🔻 Análisis de Funnel"]
    (call,) = selection.calls
    arguments = dict(call.arguments)
    yesterday = _profile_today() - timedelta(days=1)
    assert call.name == "funnel_coverage"
    assert arguments == {"profile_id": "111", "date_from": (yesterday - timedelta(days=6)).isoformat(),
                         "date_to": yesterday.isoformat(), "min_orders": 3, "match_type": "Phrase"}
    assert dict(selection.values) == {"mínimo de órdenes para harvest": "3",
                                      "match type de las campañas sugeridas": "Phrase"}


def test_a_new_minimum_reaches_the_chat_on_the_next_run(monkeypatch):
    app = _run(monkeypatch, _FakeRest())

    app.number_input(key=analisis_funnel.MIN_ORDERS_KEY).set_value(5).run()

    selection = app.session_state["app_chat_selections"]["🔻 Análisis de Funnel"]
    assert dict(selection.calls[0].arguments)["min_orders"] == 5


def test_without_synced_campaigns_the_page_asks_for_the_file_and_shares_nothing(monkeypatch):
    app = _run(monkeypatch, _FakeRest(campaign_jobs=False))

    assert "Todavía no hay métricas de campañas de esta cuenta" in _text(app)
    assert not app.tabs
    assert "🔻 Análisis de Funnel" not in app.session_state["app_chat_selections"]


def _source(source, **overrides) -> SearchTermSource:
    values = {"frame": None, "source": source, "currency_code": "MXN", "label": "Luna Kids · MX",
              "signature": "s", "attribution_days": 7, "bulk_ready": source == SOURCE_API, "profile_id": "111",
              "window_start": date(2026, 9, 14), "window_end": date(2026, 9, 20)}
    values.update(overrides)
    return SearchTermSource(**values)


def test_a_file_on_screen_tells_the_chat_the_mcp_cannot_see_it():
    selection = analisis_funnel.screen_selection(_source(SOURCE_FILE, label="str.csv", profile_id=""), min_orders=3,
                                                 match_type="Exact", campaigns_by_hand=True, older_data=False)

    assert selection.calls == () and selection.source == FROM_HAND_UPLOAD
    assert selection.notes == (HAND_UPLOAD_NOTE,)
    assert selection.profile_id == ""


def test_campaigns_by_hand_and_older_data_are_warned_to_the_chat():
    selection = analisis_funnel.screen_selection(_source(SOURCE_API), min_orders=3, match_type="Phrase",
                                                 campaigns_by_hand=True, older_data=True)

    assert selection.notes == (analisis_funnel.MANUAL_CAMPAIGNS_NOTE, OLDER_DATA_NOTE)
    assert selection.profile_id == "111"


def test_the_ai_rows_show_the_group_the_figures_and_the_verdict():
    records = [{"grupo": "harvest", "termino": "luna pajamas", "campanas": "A", "clicks": 40, "orders": 9,
                "sales": 450, "spend": 30, "acos": 6.67, "cvr": 22.5, "match_sugerido": "Exact"},
               {"grupo": "sin_trafico", "campana": "Fantasma", "presupuesto": 15, "impressions": 0, "clicks": 0,
                "spend": 0, "orders": 0, "sales": 0}]
    opinions = [{"row_id": "F02", "razon": "No entrega.", "veredicto": "INVESTIGAR", "confianza": "media",
                 "advertencia": None},
                {"row_id": "F07", "razon": "no existe", "veredicto": "ACTUAR", "confianza": "alta",
                 "advertencia": None}]

    rows = analisis_funnel.funnel_ai_rows(opinions, records, "MXN")

    assert len(rows) == 1
    assert (rows[0]["item"], rows[0]["type_tag"], rows[0]["badges"]) == ("Fantasma", "Sin tráfico", ["INVESTIGAR"])
    assert rows[0]["metrics"] == ["0 impresiones", "presupuesto MX$15.00/día"]

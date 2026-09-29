"""Análisis Cruzado over an in-memory PostgREST: the account's search terms, its SP listing and its product ads.

No network: `_open_rest` is replaced before every script run, the SQP upload and its reader are faked, and the AI
tab runs disabled except where a test fakes the provider.
"""
import csv
import io
import time
from datetime import date, datetime, timedelta, timezone

import openpyxl
import pandas as pd
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import ai.client as ai_client
import ai.runtime as ai_runtime
import modules.pages.search_term_source as search_term_source
from core.amazon_ads.structure_provider import CAMPAIGN, KEYWORD, ROW_COLUMNS
from modules.pages import analisis_cruzado
from tests.cross_analysis_data import SEARCH_TERM_COLUMNS, sqp, sqp_row, term_row

_PROFILE_TZ = "America/Los_Angeles"
SEARCH_TERMS = [
    term_row("luna pajamas", keyword_type="EXACT", cost=4.0, sales=90.0, orders=3),
    term_row("sleep sack", campaign_id="3002", ad_group_id="4002", keyword_id="5002", cost=12.0, clicks=30),
]
SQP = sqp(sqp_row("baby swaddle", purchases=60, brand_purchases=4, brand_share=6.7),
          sqp_row("luna pajamas", purchases=20, brand_share=50.0),
          sqp_row("sleep sack", purchases=3, brand_purchases=0, brand_share=0.0))
ANSWER = {"synthesis": {"situation": "La marca vende por queries que no captura.", "week_actions": ["Revisar X01"],
                        "mid_term": [], "risks": [], "executive_summary": "1 query para revisar."},
          "consultas": [{"row_id": "X01", "razon": "60 compras del mercado.", "veredicto": "ESPERAR",
                         "confianza": "media", "advertencia": "Ya existe como Exact."}]}


def _profile_today() -> date:
    return datetime.now(timezone.utc).astimezone(search_term_source.profile_timezone(_PROFILE_TZ, "")).date()


def _synced_today() -> datetime:
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(search_term_source.DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(now - timedelta(hours=1), midnight.astimezone(timezone.utc))


LISTED = _synced_today()


def _profile_row() -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids US",
            "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": _PROFILE_TZ,
            "status": "active", "data_from": (yesterday - timedelta(days=64)).isoformat(),
            "data_through": yesterday.isoformat(), "refreshed_on": _profile_today().isoformat(),
            "last_success_at": LISTED.isoformat(), "last_error": ""}


def _job_row(job_id, kind) -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"id": job_id, "integration_slug": "amazon_ads", "job_kind": kind, "trigger": "scheduled_daily",
            "external_account_id": "111", "status": "completed", "phase": "", "attempts": 0, "max_attempts": 6,
            "window_start": (yesterday - timedelta(days=64)).isoformat(), "window_end": yesterday.isoformat(),
            "local_day": _profile_today().isoformat(), "finished_at": LISTED.isoformat(),
            "created_at": LISTED.isoformat(), "warning": ""}


def _structure_row(entity, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "campaign_id": "3001", "state": "ENABLED", "metrics_known": "f",
                "listed_at": LISTED.isoformat()})
    row.update(values)
    return row


# "baby swaddle" runs as an exact keyword without a single click: only the listing knows it.
LISTING = [
    _structure_row(CAMPAIGN, entity_id="3001"),
    _structure_row(KEYWORD, ad_group_id="4001", entity_id="k1", target_text="luna pajamas", match_type="EXACT"),
    _structure_row(KEYWORD, ad_group_id="4001", entity_id="k2", target_text="baby swaddle", match_type="EXACT"),
]


def _csv(columns, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class _FakeRest:
    """The profiles, the sync jobs, the search terms, the SP listing and the product ads the page reads."""

    def __init__(self, *, profiles=True, listing=LISTING, product_ads=({"ad_group_id": "4001", "asin": "B0CYLMJJJC"},)):
        self._profiles, self._listing, self._product_ads = profiles, list(listing), list(product_ads)
        self.jobs = [_job_row(7, "sp_search_terms")]
        self.reads: list[str] = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [_profile_row()] if self._profiles else []
        if table == "integration_sync_jobs":
            kind = params.get("job_kind", "eq.sp_search_terms").removeprefix("eq.")
            return [dict(job) for job in self.jobs if job["job_kind"] == kind][:1]
        if table == "ads_product_ad":
            return [dict(row) for row in self._product_ads]
        if table in ("ads_report_requests", "ai_analysis_settings", "ai_analyses"):
            return []
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.reads.append(name)
        if name == "search_terms_between":
            return _csv(SEARCH_TERM_COLUMNS, SEARCH_TERMS)
        assert name == "sp_structure_between"
        return _csv(ROW_COLUMNS, self._listing)


class _Upload:
    def __init__(self, name: str):
        self.name = name

    def getvalue(self) -> bytes:
        return self.name.encode("utf-8")


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


@pytest.fixture(autouse=True)
def _empty_ai_registry():
    with ai_runtime._lock:
        ai_runtime._registry.clear()
    yield
    with ai_runtime._lock:
        ai_runtime._registry.clear()


_PAGE_SCRIPT = """
import streamlit as st
from core.chat import app_chat
st.cache_data.clear()
if st.session_state.get("shared_before"):
    app_chat.report_failed("cross_analysis")
from modules.pages.analisis_cruzado import render
render()
"""


def _page(monkeypatch, fake, *, sqp_uploaded=True, ai_enabled=False, downloads=None) -> AppTest:
    import streamlit
    uploads = {"sqp_x": _Upload("sqp.csv")} if sqp_uploaded else {}
    monkeypatch.setattr(streamlit, "file_uploader", lambda label, *args, key=None, **kwargs: uploads.get(key))
    monkeypatch.setattr(analisis_cruzado, "read_sqp", lambda file: SQP.copy())
    monkeypatch.setattr(analisis_cruzado, "extract_sqp_brand", lambda file: "luna")
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: fake)
    monkeypatch.setattr("ai.config.AI_ENABLED", ai_enabled)
    if downloads is not None:
        def record_download(label, data=None, **kwargs):
            downloads[label] = data
            return False
        monkeypatch.setattr(streamlit, "download_button", record_download)
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def _text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.markdown] + [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.info] + [str(element.value) for element in app.warning]
    return " ".join(parts)


def _plan_table(app: AppTest) -> pd.DataFrame:
    return app.tabs[1].dataframe[0].value


def test_without_connected_accounts_the_page_says_so_and_asks_for_no_file(monkeypatch):
    app = _page(monkeypatch, _FakeRest(profiles=False))

    assert search_term_source.NO_ACCOUNTS_MESSAGE.format(module="Análisis Cruzado") in _text(app)
    assert not app.tabs


def test_without_the_sqp_the_page_shows_the_empty_state_and_withdraws_the_analysis(monkeypatch):
    import streamlit
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: _FakeRest())
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    app.session_state["shared_before"] = True

    app.run()

    assert not app.exception
    assert not app.tabs
    assert "cross_analysis" not in app.session_state["app_chat_modules"]


def test_the_listing_marks_a_query_that_runs_as_exact_without_a_single_click(monkeypatch):
    fake = _FakeRest()

    app = _page(monkeypatch, fake)

    assert {"search_terms_between", "sp_structure_between"} <= set(fake.reads)
    local = LISTED.astimezone(search_term_source.DISPLAY_TIMEZONE)
    assert (f"Keywords Exact de la cuenta: listado de Sponsored Products de hoy {local:%H:%M} · 2 keywords Exact "
            "habilitadas.") in _text(app)
    table = _plan_table(app)
    assert dict(zip(table["Search Query"], table["♻️ Ya en Exact"])) == {"baby swaddle": True, "luna pajamas": True,
                                                                          "sleep sack": False}
    assert [tab.label for tab in app.tabs] == ["🔗 Análisis Cruzado", "🎯 Plan de Acción", "📊 PPC Insights por ASIN",
                                               "🤖 Análisis IA"]


def test_without_a_listing_the_exact_mark_is_hidden_and_the_page_says_why(monkeypatch):
    app = _page(monkeypatch, _FakeRest(listing=()))

    text = _text(app)
    assert analisis_cruzado.EXACT_NOT_LISTED_NOTE in text
    assert analisis_cruzado.EXACT_UNKNOWN_CAPTION in text
    assert "♻️ Ya en Exact" not in _plan_table(app).columns


def test_the_asin_tab_gives_each_term_the_asin_its_ad_group_advertises(monkeypatch):
    app = _page(monkeypatch, _FakeRest())

    table = app.tabs[2].dataframe[0].value
    assert list(table["ASIN"]) == ["B0CYLMJJJC"]
    assert "El 75.0% sin ASIN no entra en las cards." in _text(app)


def test_the_campaign_builder_plan_is_a_file_campaign_builder_reads_without_what_already_runs(monkeypatch):
    downloads = {}
    listing = [row for row in LISTING if row["target_text"] != "luna pajamas"]

    _page(monkeypatch, _FakeRest(listing=listing), downloads=downloads)

    builder = next(data for label, data in downloads.items() if "plan para Campaign Builder" in label)
    plan = pd.read_excel(io.BytesIO(builder))
    assert list(plan.columns[:4]) == ["Keyword", "Acción sugerida", "Purchases mercado", "Brand Share %"]
    assert plan[["Keyword", "Acción sugerida"]].values.tolist() == [["luna pajamas", "🛡️ DEFENDER marca"]]
    assert openpyxl.load_workbook(io.BytesIO(builder)).sheetnames == ["Plan de Acción", "Fuera del plan"]
    left_out = pd.read_excel(io.BytesIO(builder), sheet_name="Fuera del plan")
    assert dict(zip(left_out["Keyword"], left_out["Motivo"])) == {
        "baby swaddle": "Ya existe como keyword Exact habilitada en la cuenta: Campaign Builder crearía otra igual.",
        "sleep sack": "Campaign Builder sólo arma campañas nuevas de ESCALAR, AGREGAR y DEFENDER."}


def test_without_a_price_the_amazon_bulk_is_not_offered_and_the_analysis_is(monkeypatch):
    downloads = {}

    app = _page(monkeypatch, _FakeRest(), downloads=downloads)

    assert not any("Plan de Acción bulk" in label for label in downloads)
    assert any("NO subible" in label for label in downloads)
    assert analisis_cruzado.NO_PRICE_ERROR in [str(error.value) for error in app.error]


def test_the_ai_analysis_waits_for_the_click_and_reaches_the_chat_with_the_account(monkeypatch):
    calls = []

    def ask(**call):
        calls.append(call)
        return {"structured_output": ANSWER, "session_id": "cross-session"}

    monkeypatch.setattr(ai_client, "ask", ask)
    app = _page(monkeypatch, _FakeRest(), ai_enabled=True)

    assert calls == []
    app.button(key="cross_analysis_ai_recalc").click().run()
    for _ in range(30):
        entry = app.session_state["app_chat_modules"].get("cross_analysis")
        if entry is not None and entry.state == "current":
            break
        time.sleep(0.2)
        app.run()

    assert not app.exception, app.exception
    assert len(calls) == 1
    shared = app.session_state["app_chat_modules"]["cross_analysis"].analysis
    titles = [document["title"] for document in shared.documents]
    assert titles[0] == "Análisis Cruzado · Luna Kids · US · Parámetros"
    assert titles[-1] == "Análisis Cruzado · Luna Kids · US · Lectura de la IA"
    assert (shared.profile_id, shared.country_code) == ("111", "US")
    assert shared.annotate("Revisar X01").startswith("Revisar X01 (")

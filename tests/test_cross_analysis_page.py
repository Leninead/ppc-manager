"""Análisis Cruzado over an in-memory PostgREST: the account's search terms, its SP listing and its product ads, or a
Bulk File uploaded by hand.

No network: `_open_rest` is replaced before every script run, the uploads and the SQP reader are faked, and the AI
tab runs disabled except where a test fakes the provider.
"""
import csv
import io
import json
import time
from datetime import date, datetime, timedelta, timezone

import openpyxl
import pandas as pd
import pytest
import requests
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import ai.client as ai_client
import ai.runtime as ai_runtime
import modules.pages.search_term_source as search_term_source
from core.amazon_ads.structure_provider import CAMPAIGN, KEYWORD, ROW_COLUMNS
from core.cross_analysis.action_plan import ACTION_DEFEND
from core.cross_analysis.asin_summary import ACOS, AD_SALES, AD_SPEND, ASIN, BR_SALES, BR_SESSIONS, CVR
from modules.pages import analisis_cruzado
from tests.cross_analysis_data import SEARCH_TERM_COLUMNS, sqp, sqp_row, term_row
from tests.test_bulk_parser import _asegurar_fixture as synthetic_bulk_file
from tests.test_cross_analysis_bulk_file import OLE_COMPOUND_FILE, bulk_workbook

_PROFILE_TZ = "America/Los_Angeles"
SEARCH_TERMS = [
    term_row("luna pajamas", keyword_type="EXACT", cost=4.0, sales=90.0, orders=3),
    term_row("sleep sack", campaign_id="3002", ad_group_id="4002", keyword_id="5002", cost=12.0, clicks=30),
]
SQP = sqp(sqp_row("baby swaddle", purchases=60, brand_purchases=4, brand_share=6.7),
          sqp_row("luna pajamas", purchases=20, brand_share=50.0),
          sqp_row("sleep sack", purchases=3, brand_purchases=0, brand_share=0.0))
# The synthetic Bulk File's terms (tests/fixtures/make_bulk_fixture.py), with "merino" as the brand.
BULK_SQP = sqp(sqp_row("organic cotton sleep sack", purchases=40, brand_purchases=5, brand_share=12.5),
               sqp_row("merino wool swaddle blanket", purchases=30, brand_purchases=3, brand_share=10.0),
               sqp_row("nordic sleep bag", purchases=20, brand_share=50.0))
TAB_LABELS = ["🔗 Análisis Cruzado", "🎯 Plan de Acción", "📊 PPC Insights por ASIN", "🤖 Análisis IA"]
BULK_FILE_KEY = "cruzado_src_file"
BUSINESS_REPORT_KEY = "cruzado_br_asin"
BUSINESS_REPORT_COLUMNS = ["(Parent) ASIN", "(Child) ASIN", "Title", "Sessions - Total", "Ordered Product Sales"]
UPLOAD_BUTTON_KEY = "cruzado_bulk_src_upload_manual"
ZERO_IMPRESSION_ITEMS = "Campaign items with zero impressions"
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


def _profile_row(*, synced=True) -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids US",
            "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": _PROFILE_TZ,
            "status": "active", "data_from": (yesterday - timedelta(days=64)).isoformat() if synced else None,
            "data_through": yesterday.isoformat() if synced else None, "refreshed_on": _profile_today().isoformat(),
            "last_success_at": LISTED.isoformat() if synced else None, "last_error": ""}


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

    def __init__(self, *, profiles=True, synced=True, search_terms=SEARCH_TERMS, listing=LISTING,
                 product_ads=({"ad_group_id": "4001", "asin": "B0CYLMJJJC"},), unreadable=()):
        self._profiles, self._synced, self._search_terms = profiles, synced, list(search_terms)
        self._listing, self._product_ads, self._unreadable = list(listing), list(product_ads), set(unreadable)
        self.jobs = [_job_row(7, "sp_search_terms")]
        self.reads: list[str] = []
        self.selects: list[str] = []

    def select(self, table, params):
        self.selects.append(table)
        if table in self._unreadable:
            raise requests.ConnectionError(f"{table} is down")
        if table == "ads_profile_sync":
            return [_profile_row(synced=self._synced)] if self._profiles else []
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
        if name in self._unreadable:
            raise requests.ConnectionError(f"{name} is down")
        if name == "search_terms_between":
            return _csv(SEARCH_TERM_COLUMNS, self._search_terms)
        assert name == "sp_structure_between"
        return _csv(ROW_COLUMNS, self._listing)


class _Upload:
    def __init__(self, name: str, data: bytes | None = None):
        self.name, self._data = name, name.encode("utf-8") if data is None else data

    def getvalue(self) -> bytes:
        return self._data


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


def _page(monkeypatch, fake, *, sqp_uploaded=True, bulk=None, business_report=None, sqp_table=SQP, brand="luna",
          session=None, ai_enabled=False, downloads=None) -> AppTest:
    import streamlit
    uploads = {"sqp_x": _Upload("sqp.csv")} if sqp_uploaded else {}
    if bulk is not None:
        uploads[BULK_FILE_KEY] = bulk
    if business_report is not None:
        uploads[BUSINESS_REPORT_KEY] = business_report
    monkeypatch.setattr(streamlit, "file_uploader", lambda label, *args, key=None, **kwargs: uploads.get(key))
    monkeypatch.setattr(analisis_cruzado, "read_sqp", lambda file: sqp_table.copy())
    monkeypatch.setattr(analisis_cruzado, "extract_sqp_brand", lambda file: brand)
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: fake)
    monkeypatch.setattr("ai.config.AI_ENABLED", ai_enabled)
    if downloads is not None:
        def record_download(label, data=None, **kwargs):
            downloads[label] = data
            return False
        monkeypatch.setattr(streamlit, "download_button", record_download)
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    for key, value in (session or {}).items():
        app.session_state[key] = value
    app.run()
    assert not app.exception, app.exception
    return app


def _bulk_file() -> _Upload:
    return _Upload("bulk.xlsx", synthetic_bulk_file().read_bytes())


def _text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.markdown] + [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.info] + [str(element.value) for element in app.warning]
    return " ".join(parts)


def _button_keys(app: AppTest) -> list[str]:
    return [button.key for button in app.button]


def _plan_table(app: AppTest) -> pd.DataFrame:
    return app.tabs[1].dataframe[0].value


def _plan_captions(app: AppTest) -> list[str]:
    return [str(caption.value) for caption in app.tabs[1].caption]


def test_without_connected_accounts_the_page_asks_for_the_bulk_file(monkeypatch):
    app = _page(monkeypatch, _FakeRest(profiles=False))

    text = _text(app)
    assert analisis_cruzado.NO_CONNECTION_BULK_HINT in text and search_term_source.NO_CONNECTION_HINT not in text
    assert "El SQP se sigue subiendo a mano." in analisis_cruzado.NO_CONNECTION_BULK_HINT
    assert "Subí el Bulk File para cruzar sus search terms con el SQP de la marca." in text
    assert not app.tabs


def test_the_help_says_to_include_the_keywords_without_impressions_in_the_bulk_file(monkeypatch):
    app = _page(monkeypatch, _FakeRest(profiles=False))

    assert any(ZERO_IMPRESSION_ITEMS in str(block.value) and "Exclude" in str(block.value) for block in app.markdown)


def test_a_bulk_file_without_accounts_runs_the_four_tabs_without_reading_amazon_ads(monkeypatch):
    fake = _FakeRest(profiles=False)

    app = _page(monkeypatch, fake, bulk=_bulk_file(), sqp_table=BULK_SQP, brand="merino")

    assert [tab.label for tab in app.tabs] == TAB_LABELS
    assert fake.reads == [] and set(fake.selects) == {"ads_profile_sync"}
    text = _text(app)
    assert "Keywords Exact que trae la hoja de campañas del Bulk File · 4 keywords Exact habilitadas." in text
    assert analisis_cruzado.BULK_UNSTATED_NOTE in text
    captions = _plan_captions(app)
    assert analisis_cruzado.BULK_GUARDS_CAPTION in captions and analisis_cruzado.GUARDS_CAPTION not in captions
    assert "tenga o no clicks" not in analisis_cruzado.BULK_GUARDS_CAPTION
    assert ZERO_IMPRESSION_ITEMS in analisis_cruzado.BULK_GUARDS_CAPTION
    table = _plan_table(app)
    assert dict(zip(table["Search Query"], table["♻️ Ya en Exact"])) == {
        "organic cotton sleep sack": True, "merino wool swaddle blanket": False, "nordic sleep bag": True}
    assert dict(zip(table["Search Query"], table["🏅 Ranking KW"]))["merino wool swaddle blanket"]


def test_the_listing_line_offers_the_bulk_file_and_manual_mode_reads_no_amazon_ads(monkeypatch):
    fake = _FakeRest()
    app = _page(monkeypatch, fake)
    assert _button_keys(app).count(UPLOAD_BUTTON_KEY) == 1
    reads = len(fake.reads)

    app.button(key=UPLOAD_BUTTON_KEY).click().run()

    assert not app.exception, app.exception
    assert search_term_source.MANUAL_MODE_NOTE in _text(app)
    assert "Subí el Bulk File para cruzar sus search terms con el SQP de la marca." in _text(app)
    assert not app.tabs and len(fake.reads) == reads
    app.button(key="cruzado_src_back_to_api").click().run()
    assert [tab.label for tab in app.tabs] == TAB_LABELS
    assert search_term_source.MANUAL_MODE_NOTE not in _text(app)


def test_an_account_without_data_yet_offers_the_bulk_file(monkeypatch):
    app = _page(monkeypatch, _FakeRest(synced=False))

    assert not app.tabs
    assert _button_keys(app).count(UPLOAD_BUTTON_KEY) == 1


def test_an_unreadable_listing_or_product_ads_still_offers_the_bulk_file(monkeypatch):
    app = _page(monkeypatch, _FakeRest(unreadable=("sp_structure_between", "ads_product_ad")))

    text = _text(app)
    assert analisis_cruzado.EXACT_UNREADABLE_NOTE in text and analisis_cruzado.ADVERTISED_ASINS_UNREADABLE in text
    assert _button_keys(app).count(UPLOAD_BUTTON_KEY) == 1
    assert [tab.label for tab in app.tabs] == TAB_LABELS


def test_a_file_that_is_not_a_workbook_says_so_and_shows_no_tabs(monkeypatch):
    app = _page(monkeypatch, _FakeRest(profiles=False), bulk=_Upload("notas.xlsx", b"not a workbook"))

    assert any("No se pudo leer «notas.xlsx»" in str(error.value) for error in app.error)
    assert not app.tabs


def test_an_encrypted_or_legacy_excel_file_says_so_instead_of_a_traceback(monkeypatch):
    app = _page(monkeypatch, _FakeRest(profiles=False), bulk=_Upload("bulk-protegido.xlsx", OLE_COMPOUND_FILE))

    assert any("No se pudo leer «bulk-protegido.xlsx»" in str(error.value) for error in app.error)
    assert not app.tabs


def test_a_bulk_file_without_the_campaigns_sheet_warns_and_hides_the_exact_mark(monkeypatch):
    bulk = _Upload("bulk.xlsx", bulk_workbook(campaigns=False))

    app = _page(monkeypatch, _FakeRest(profiles=False), bulk=bulk, sqp_table=BULK_SQP, brand="merino")

    text = _text(app)
    assert analisis_cruzado.NO_CAMPAIGNS_SHEET_WARNING in text and analisis_cruzado.BULK_EXACT_UNKNOWN_CAPTION in text
    assert "Sin listado" not in text
    captions = _plan_captions(app)
    assert ("Sin la hoja de campañas del Bulk File no se pudo verificar si las keywords a agregar ya existen como "
            "Exact: revisalas en Campaign Manager antes de subir el archivo.") in captions
    assert ("Sin la hoja de campañas del Bulk File no se pudo verificar cuáles ya existen como keyword Exact: "
            "revisalas en Campaign Manager antes de lanzarlas.") in captions
    assert "♻️ Ya en Exact" not in _plan_table(app).columns


def test_both_exports_of_a_bulk_file_carry_the_files_ids(monkeypatch):
    downloads = {}
    app = _page(monkeypatch, _FakeRest(), bulk=_bulk_file(), sqp_table=BULK_SQP, brand="merino",
                session={"cruzado_src_manual": True}, downloads=downloads)

    app.number_input(key="ac_precio_prom").set_value(20.0).run()

    assert not app.exception, app.exception
    bulk = next(data for label, data in downloads.items() if "Plan de Acción bulk" in label)
    sheet = pd.read_excel(io.BytesIO(bulk), sheet_name="Sponsored Products Campaigns", dtype=str)
    assert sorted(sheet[["Campaign ID", "Ad Group ID", "Keyword ID"]].fillna("").values.tolist()) == [
        ["132313349237695", "900000000000101", ""],
        ["132313349237695", "900000000000101", "409151500000001"],
        ["214785693021447", "900000000000202", "409151500000006"]]
    builder = next(data for label, data in downloads.items() if "plan para Campaign Builder" in label)
    plan = pd.read_excel(io.BytesIO(builder))
    assert plan[["Keyword", "Acción sugerida"]].values.tolist() == [["merino wool swaddle blanket", ACTION_DEFEND]]
    left_out = pd.read_excel(io.BytesIO(builder), sheet_name="Fuera del plan")
    assert dict(zip(left_out["Keyword"], left_out["Motivo"]))["organic cotton sleep sack"] == (
        "Ya existe como keyword Exact habilitada en la cuenta: Campaign Builder crearía otra igual.")


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
    captions = _plan_captions(app)
    assert analisis_cruzado.GUARDS_CAPTION in captions and analisis_cruzado.BULK_GUARDS_CAPTION not in captions
    assert [tab.label for tab in app.tabs] == ["🔗 Análisis Cruzado", "🎯 Plan de Acción", "📊 PPC Insights por ASIN",
                                               "🤖 Análisis IA"]


def test_without_a_listing_the_exact_mark_is_hidden_and_the_page_says_why(monkeypatch):
    app = _page(monkeypatch, _FakeRest(listing=()))

    text = _text(app)
    assert analisis_cruzado.EXACT_NOT_LISTED_NOTE in text
    assert analisis_cruzado.EXACT_UNKNOWN_CAPTION in text
    assert ("Sin listado de la cuenta no se pudo verificar si las keywords a agregar ya existen como Exact: revisalas "
            "en Campaign Manager antes de subir el archivo.") in _plan_captions(app)
    assert "♻️ Ya en Exact" not in _plan_table(app).columns


def test_an_accounts_outage_with_data_on_screen_reads_the_accounts_no_more_than_the_picker_does(monkeypatch):
    fake = _FakeRest()
    app = _page(monkeypatch, fake)
    fake._unreadable.add("ads_profile_sync")
    selects = len(fake.selects)

    app.run()

    assert not app.exception, app.exception
    assert fake.selects[selects:].count("ads_profile_sync") == 2
    assert search_term_source.ACCOUNTS_UNREADABLE_MESSAGE in _text(app)
    assert [tab.label for tab in app.tabs] == TAB_LABELS


def test_the_asin_tab_gives_each_term_the_asin_its_ad_group_advertises(monkeypatch):
    app = _page(monkeypatch, _FakeRest())

    table = app.tabs[2].dataframe[0].value
    assert list(table["ASIN"]) == ["B0CYLMJJJC"]
    assert "El 75.0% sin ASIN no entra en las cards." in _text(app)


def test_the_asin_table_shows_one_decimal_percents_and_the_sessions_with_thousands_separators(monkeypatch):
    search_terms = [term_row("luna pajamas", keyword_type="EXACT", cost=8.6, sales=100.0, orders=11, clicks=200),
                    term_row("sleep sack", campaign_id="3002", ad_group_id="4002", keyword_id="5002", cost=12.0,
                             clicks=30)]
    product_ads = ({"ad_group_id": "4001", "asin": "B0CYLMJJJC"}, {"ad_group_id": "4002", "asin": "B0LUNA0002"})
    business_report = _Upload("br.csv", _csv(BUSINESS_REPORT_COLUMNS, [
        {"(Parent) ASIN": "B0LUNA0000", "(Child) ASIN": "B0CYLMJJJC", "Title": "Luna Pajamas",
         "Sessions - Total": "2,900", "Ordered Product Sales": "$1,234.56"}]))

    app = _page(monkeypatch, _FakeRest(search_terms=search_terms, product_ads=product_ads),
                business_report=business_report)

    table = app.tabs[2].dataframe[0]
    formats = {column: config["type_config"]["format"] for column, config in json.loads(table.proto.columns).items()
               if "format" in config.get("type_config", {})}
    assert formats == {AD_SPEND: "$%.2f", AD_SALES: "$%.2f", ACOS: "%.1f%%", CVR: "%.1f%%", BR_SALES: "$%.2f"}
    styler_text = convert_arrow_bytes_to_pandas_df(table.proto.styler.display_values)
    assert styler_text[BR_SESSIONS].tolist() == ["", "2,900"]
    rows = table.value
    assert rows[ASIN].tolist() == ["B0LUNA0002", "B0CYLMJJJC"]
    assert pd.isna(rows[ACOS].iloc[0]) and rows[[ACOS, CVR]].iloc[1].tolist() == [8.6, 5.5]
    assert "#E8F5E9" in table.proto.styler.styles


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


def test_the_ai_analysis_of_a_bulk_file_names_the_file_and_no_account(monkeypatch):
    calls = []

    def ask(**call):
        calls.append(call)
        return {"structured_output": ANSWER, "session_id": "cross-bulk-session"}

    monkeypatch.setattr(ai_client, "ask", ask)
    app = _page(monkeypatch, _FakeRest(profiles=False), bulk=_bulk_file(), sqp_table=BULK_SQP, brand="merino",
                ai_enabled=True)

    app.button(key="cross_analysis_ai_recalc").click().run()
    for _ in range(30):
        entry = app.session_state["app_chat_modules"].get("cross_analysis")
        if entry is not None and entry.state == "current":
            break
        time.sleep(0.2)
        app.run()

    assert not app.exception, app.exception
    params = calls[0]["context"][0]["content"]
    assert "Search terms: Bulk File subido a mano «bulk.xlsx», no una cuenta de Amazon Ads conectada" in params
    assert ("Keywords Exact de la cuenta: hoja de campañas del Bulk File, que trae 4 keywords Exact habilitadas; si se "
            "bajó sin «Campaign items with zero impressions», no trae las que no tuvieron impresiones") in params
    shared = app.session_state["app_chat_modules"]["cross_analysis"].analysis
    assert shared.documents[0]["title"] == "Análisis Cruzado · bulk.xlsx · Parámetros"
    assert (shared.profile_id, shared.country_code) == ("", "")

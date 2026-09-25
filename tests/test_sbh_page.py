"""SBH Recommendation over an in-memory PostgREST: the chosen account's SP listing marks «En SP», never a default one.

No network: `_open_rest` is replaced before every script run, the uploads and their parsers are faked, and the AI
tab runs disabled except where a test fakes the provider.
"""
import csv
import io
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import requests
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import ai.client as ai_client
import ai.runtime as ai_runtime
import modules.pages.search_term_source as search_term_source
from core import ai_tab
from core.amazon_ads.structure_provider import AD_GROUP, CAMPAIGN, KEYWORD, ROW_COLUMNS
from core.sbh.analysis import build_analysis_input
from core.sbh.targets import SpKeywordCoverage, query_shares, recommend_targets
from modules.pages import sbh_recommendation as sbh_page

ACCOUNT = "Luna Kids"
MKL = pd.DataFrame([{"Search Term": term, "SV": sv, "Relevance": 3.4, "Sugg. Bid": 1.2, "Launch Score": 8.0}
                    for term, sv in (("vitamin a cream", 3000), ("vitamin c serum", 1500),
                                     ("night vitamin oil", 700), ("baby lotion", 400))])
SQP = pd.DataFrame({"Search Query": ["vitamin a cream", "baby lotion"],
                    "Impressions: Total Count": [90000, 800], "Impressions: Brand Count": [1800, 240],
                    "Purchases: Total Count": [300, 12], "Purchases: Brand Count": [3, 3],
                    "Reporting Date": ["2026-09-20", "2026-09-20"]})
ANSWER = {"synthesis": {"situation": "La marca casi no aparece en vitamin.", "week_actions": ["Lanzar G01"],
                        "mid_term": [], "risks": [], "executive_summary": "1 cluster para lanzar."},
          "clusters": [{"row_id": "G01", "razon": "5.200 búsquedas con la marca en 1,2%.", "veredicto": "LANZAR",
                        "confianza": "alta", "headline": "Vitamin A cream for night skin", "advertencia": None}]}


def _listed_today() -> datetime:
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(search_term_source.DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(now - timedelta(hours=1), midnight.astimezone(timezone.utc))


LISTED = _listed_today()


def _profile_row() -> dict:
    today = datetime.now(timezone.utc).date()
    return {"profile_id": "111", "account_id": 1, "cliente": ACCOUNT, "account_name": "Luna Kids US",
            "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "America/New_York",
            "status": "active", "data_from": (today - timedelta(days=65)).isoformat(),
            "data_through": (today - timedelta(days=1)).isoformat(), "refreshed_on": today.isoformat(),
            "last_success_at": LISTED.isoformat(), "last_error": ""}


def _structure_row(entity, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "campaign_id": "1", "state": "ENABLED", "metrics_known": "f",
                "listed_at": LISTED.isoformat()})
    row.update(values)
    return row


CAMPAIGN_ROW = _structure_row(CAMPAIGN, entity_id="1")
LISTED_ACCOUNT = [
    CAMPAIGN_ROW,
    _structure_row(AD_GROUP, ad_group_id="10", entity_id="10"),
    _structure_row(KEYWORD, ad_group_id="10", entity_id="k1", target_kind="keyword", target_text="Vitamin C Serum",
                   match_type="EXACT"),
    _structure_row(KEYWORD, ad_group_id="10", entity_id="k2", target_kind="keyword", target_text="night vitamin oil",
                   match_type="BROAD", state="PAUSED"),
]


def _job_row(kind, *, warning="") -> dict:
    return {"id": 9, "integration_slug": "amazon_ads", "job_kind": kind, "trigger": "scheduled_daily",
            "external_account_id": "111", "status": "completed", "warning": warning,
            "finished_at": LISTED.isoformat(), "created_at": LISTED.isoformat()}


class _FakeRest:
    """The profile table, the completed listing jobs, and the SP structure read."""

    def __init__(self, *, profiles=True, structure=LISTED_ACCOUNT, jobs=(), fail=False):
        self._profiles, self._structure, self._jobs, self._fail = profiles, list(structure), list(jobs), fail
        self.reads: list[tuple[str, dict]] = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [_profile_row()] if self._profiles else []
        if table == "integration_sync_jobs":
            kind = params.get("job_kind", "").removeprefix("eq.")
            return [dict(job) for job in self._jobs if job["job_kind"] == kind][:1]
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.reads.append((name, args))
        if self._fail:
            raise requests.ConnectionError("gateway down")
        assert name == "sp_structure_between"
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(ROW_COLUMNS))
        writer.writeheader()
        writer.writerows(self._structure)
        return buffer.getvalue().encode("utf-8")


class _Upload:
    def __init__(self, name: str):
        self.name = name

    def getvalue(self) -> bytes:
        return self.name.encode("utf-8")

    def seek(self, offset: int) -> None:
        return None


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
    app_chat.report_failed("sbh")
from modules.pages.sbh_recommendation import render
render()
"""


def _page(monkeypatch, fake, *, files=True, ai_enabled=False) -> AppTest:
    import streamlit
    uploads = {"sbh_mkl": _Upload("niche-luna-keywords.xlsx"), "sbh_sqp": _Upload("sqp.csv")} if files else {}
    monkeypatch.setattr(streamlit, "file_uploader", lambda label, *args, key=None, **kwargs: uploads.get(key))
    monkeypatch.setattr(sbh_page, "_parse_mkl", lambda data, name: (MKL.copy(), []))
    monkeypatch.setattr(sbh_page, "read_sqp", lambda file: SQP.copy())
    monkeypatch.setattr(sbh_page, "extract_sqp_brand", lambda file: "luna")
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: fake)
    monkeypatch.setattr("ai.config.AI_ENABLED", ai_enabled)
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def _choose_account(app: AppTest) -> AppTest:
    app.selectbox(key="sbh_src_account").set_value(ACCOUNT).run()
    assert not app.exception, app.exception
    return app


def _text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.markdown] + [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.error] + [str(element.value) for element in app.info]
    return " ".join(parts)


def _in_sp(app: AppTest) -> dict:
    """The «En SP» column as shown: the priority filter starts on ALTA and MEDIA."""
    table = app.tabs[0].dataframe[0].value
    return dict(zip(table["Keyword"], table["En SP"]))


def test_before_choosing_an_account_nothing_is_read_and_in_sp_is_unknown(monkeypatch):
    fake = _FakeRest()

    app = _page(monkeypatch, fake)

    assert fake.reads == []
    assert app.selectbox(key="sbh_src_account").value is None
    assert sbh_page.CHOOSE_ACCOUNT_NOTE in _text(app)
    assert [tab.label for tab in app.tabs] == ["📢 Targets", "🤖 Análisis IA"]
    assert set(_in_sp(app).values()) == {"—"}
    assert sbh_page.IN_SP_UNKNOWN_CAPTION in _text(app)


def test_the_chosen_account_marks_the_keywords_that_run_in_its_sp_listing(monkeypatch):
    fake = _FakeRest()

    app = _choose_account(_page(monkeypatch, fake))

    reads = {(name, args["p_profile_id"], tuple(args["p_entities"])) for name, args in fake.reads}
    assert reads == {("sp_structure_between", "111", ("campaign", "ad_group", "keyword"))}
    assert _in_sp(app) == {"vitamin a cream": "❌", "vitamin c serum": "✅", "night vitamin oil": "❌"}
    local = LISTED.astimezone(search_term_source.DISPLAY_TIMEZONE)
    text = _text(app)
    assert f"Listadas hoy {local:%H:%M}" in text
    assert "1 keyword activa" in text
    assert "Sponsored Products de Luna Kids · US" in text and f"listado de hoy {local:%H:%M}" in text


def test_a_listing_that_cannot_be_read_says_so_and_the_module_still_recommends(monkeypatch):
    app = _choose_account(_page(monkeypatch, _FakeRest(fail=True)))

    assert any(sbh_page.UNREADABLE_NOTE in str(error.value) for error in app.error)
    assert set(_in_sp(app).values()) == {"—"}


def test_an_account_never_listed_leaves_in_sp_unknown(monkeypatch):
    app = _choose_account(_page(monkeypatch, _FakeRest(structure=())))

    assert sbh_page.NOT_LISTED_NOTE in _text(app)
    assert set(_in_sp(app).values()) == {"—"}


def test_an_account_listed_without_keywords_has_none_of_them_in_sp(monkeypatch):
    app = _choose_account(_page(monkeypatch, _FakeRest(structure=[CAMPAIGN_ROW], jobs=[_job_row("sp_targets")])))

    assert "0 keywords activas" in _text(app)
    assert set(_in_sp(app).values()) == {"❌"}


def test_a_keyword_listing_amazon_refused_says_so_and_is_not_an_empty_one(monkeypatch):
    refused = _job_row("sp_targets", warning="sin permiso para leer keywords y targets")

    app = _choose_account(_page(monkeypatch, _FakeRest(structure=[CAMPAIGN_ROW], jobs=[refused])))

    text = _text(app)
    assert sbh_page.REFUSED_NOTE.format(refusal="sin permiso para leer keywords y targets") in text
    assert "Sin permiso" in text and sbh_page.NOT_LISTED_NOTE not in text
    assert set(_in_sp(app).values()) == {"—"}


def test_without_connected_accounts_the_page_says_so_and_still_recommends(monkeypatch):
    app = _page(monkeypatch, _FakeRest(profiles=False))

    assert sbh_page.NO_ACCOUNTS_NOTE in _text(app)
    assert not app.selectbox
    assert set(_in_sp(app).values()) == {"—"}


def test_without_the_files_the_page_shows_the_empty_state_and_withdraws_the_analysis(monkeypatch):
    import streamlit
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: _FakeRest())
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    app.session_state["shared_before"] = True

    app.run()

    assert not app.exception
    assert not app.tabs
    assert "sbh" not in app.session_state["app_chat_modules"]


def test_the_ai_analysis_waits_for_the_click_and_reaches_the_chat_with_the_account(monkeypatch):
    calls = []

    def ask(**call):
        calls.append(call)
        return {"structured_output": ANSWER, "session_id": "sbh-session"}

    monkeypatch.setattr(ai_client, "ask", ask)
    app = _choose_account(_page(monkeypatch, _FakeRest(), ai_enabled=True))

    assert calls == []
    app.button(key="sbh_ai_recalc").click().run()
    for _ in range(30):
        entry = app.session_state["app_chat_modules"].get("sbh")
        if entry is not None and entry.state == "current":
            break
        time.sleep(0.2)
        app.run()

    assert not app.exception, app.exception
    assert len(calls) == 1
    shared = app.session_state["app_chat_modules"]["sbh"].analysis
    titles = [document["title"] for document in shared.documents]
    assert titles[0] == "SBH Recommendation · marca luna · Parámetros"
    assert titles[-1] == "SBH Recommendation · marca luna · Lectura de la IA"
    assert "G01 · vitamin → LANZAR · alta" in shared.documents[-1]["content"]
    assert "Cuenta de Amazon Ads de la columna en_sp: Luna Kids · US" in shared.documents[0]["content"]
    assert (shared.profile_id, shared.country_code) == ("111", "US")
    assert shared.annotate("Lanzar G01") == "Lanzar G01 (vitamin)"


def test_the_ai_rows_warn_about_a_headline_longer_than_campaign_builder_takes():
    targets = recommend_targets(MKL, query_shares(SQP), frozenset())
    records = build_analysis_input(targets, SpKeywordCoverage(), brand="luna", mkl_keywords=4, sqp_queries=2,
                                   lang="es").records
    labels = ai_tab.ai_labels("es", sbh_page._AI_TEXTS["es"])
    headline = "Vitamin A cream for night skin that works while you sleep"
    opinions = [{"row_id": "G01", "razon": "Mucho volumen.", "veredicto": "LANZAR", "confianza": "media",
                 "headline": headline, "advertencia": None},
                {"row_id": "G77", "razon": "no existe", "veredicto": "PROBAR", "confianza": "baja",
                 "headline": None, "advertencia": None}]

    rows = sbh_page.sbh_ai_rows(opinions, records, labels)

    assert len(rows) == 1
    assert rows[0]["item"] == "vitamin" and rows[0]["badges"] == ["LANZAR"]
    assert rows[0]["metrics"] == ["SV 5.200", "1 ALTA", "En SP sin dato", "IS 1.2%"]
    assert rows[0]["warning"] == f"El headline propuesto tiene {len(headline)} caracteres y el Campaign Builder acepta hasta 50."
    assert rows[0]["reasoning"] == f"Mucho volumen. Headline propuesto: «{headline}» ({len(headline)} caracteres)."

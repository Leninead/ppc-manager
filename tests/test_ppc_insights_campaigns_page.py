"""PPC Insights over an in-memory PostgREST: the campaigns come from the SP listing of the picker's account, or from a
Campaign CSV uploaded by hand.

No network: `_open_rest` is replaced before every script run, the uploads are faked, and the AI tab runs disabled.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import ButtonGroup

import ai.runtime as ai_runtime
import modules.pages.search_term_source as search_term_source
from core.amazon_ads.sync_planner import SP_PRODUCT_ADS_KIND
from modules.pages import insights_campaign_source
from tests.cross_analysis_data import search_terms_csv, term_row
from tests.ppc_insights_campaigns_data import ListingRest, campaign, completed_job, keyword, product_ad

_PROFILE_TZ = "America/Los_Angeles"
HERO = "B0CYLMJJJC"
SEARCH_TERMS = [term_row("luna pajamas", keyword_type="EXACT", cost=4.0, sales=90.0, orders=3)]
LISTING = [
    campaign("3001", "Luna - SP - KW - Exact"), product_ad("3001", "4001", HERO),
    keyword("3001", "4001", "luna pajamas", "EXACT"),
    campaign("3002", "Luna - SP - Auto", targeting="AUTO"), product_ad("3002", "4002", HERO),
]


def _profile_today() -> date:
    return datetime.now(timezone.utc).astimezone(search_term_source.profile_timezone(_PROFILE_TZ, "")).date()


def _synced_today() -> datetime:
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(search_term_source.DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(now - timedelta(hours=1), midnight.astimezone(timezone.utc))


SYNCED = _synced_today()


def _profile_row() -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids US",
            "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": _PROFILE_TZ,
            "status": "active", "data_from": (yesterday - timedelta(days=64)).isoformat(),
            "data_through": yesterday.isoformat(), "refreshed_on": _profile_today().isoformat(),
            "last_success_at": SYNCED.isoformat(), "last_error": ""}


def _search_terms_job() -> dict:
    yesterday = _profile_today() - timedelta(days=1)
    return {"id": 7, "integration_slug": "amazon_ads", "job_kind": "sp_search_terms", "trigger": "scheduled_daily",
            "external_account_id": "111", "status": "completed", "phase": "", "attempts": 0, "max_attempts": 6,
            "window_start": (yesterday - timedelta(days=64)).isoformat(), "window_end": yesterday.isoformat(),
            "local_day": _profile_today().isoformat(), "finished_at": SYNCED.isoformat(),
            "created_at": SYNCED.isoformat(), "warning": ""}


class _FakeRest(ListingRest):
    """The profile, the search terms, the product ads and the SP listing the page reads."""

    def __init__(self, listing=LISTING, *, jobs=(), fail_listing=False):
        super().__init__(listing, jobs=[_search_terms_job(), *jobs], fail=fail_listing)

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [_profile_row()]
        if table == "ads_product_ad":
            return [{"ad_group_id": "4001", "asin": HERO}, {"ad_group_id": "4002", "asin": HERO}]
        if table in ("ads_report_requests", "ai_analysis_settings", "ai_analyses"):
            return []
        return super().select(table, params)

    def rpc_csv(self, name, args, *, timeout_s=8):
        if name == "search_terms_between":
            return search_terms_csv(SEARCH_TERMS)
        return super().rpc_csv(name, args, timeout_s=timeout_s)


class _Upload:
    def __init__(self, name: str, content: bytes):
        self.name, self._content = name, content

    def getvalue(self) -> bytes:
        return self._content


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
st.cache_data.clear()
from modules.pages.ppc_insights import render
render()
"""


def _page(monkeypatch, fake, *, uploads=None) -> AppTest:
    import streamlit
    uploads = uploads or {}
    monkeypatch.setattr(streamlit, "file_uploader", lambda label, *args, key=None, **kwargs: uploads.get(key))
    monkeypatch.setattr(search_term_source, "_open_rest", lambda: fake)
    monkeypatch.setattr("ai.config.AI_ENABLED", False)
    app = AppTest.from_string(_PAGE_SCRIPT, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def _generate(app: AppTest) -> AppTest:
    app.button(key="insights_run").click().run()
    assert not app.exception, app.exception
    return app


def _text(app: AppTest) -> str:
    parts = [str(element.value) for element in app.markdown] + [str(element.value) for element in app.caption]
    parts += [str(element.value) for element in app.info] + [str(element.value) for element in app.warning]
    parts += [str(element.value) for element in app.error] + [str(element.value) for element in app.success]
    return " ".join(parts)


def _metrics(app: AppTest) -> dict:
    return {element.label: element.value for element in app.metric}


def test_the_picker_account_brings_its_campaigns_and_each_asin_scores_their_structure(monkeypatch):
    fake = _FakeRest()

    app = _generate(_page(monkeypatch, fake))

    listing_reads = [args for args in fake.reads if "p_entities" in args]
    assert listing_reads and all(args["p_profile_id"] == "111" for args in listing_reads)
    text = _text(app)
    assert "Campañas de la cuenta" in text and "Listadas" in text
    assert "2 campañas SP habilitadas" in text and "2 ad groups con anuncios" in text
    assert [button.label for button in app.button if button.key.startswith("insights_campaigns")] == [
        "Subir Campaign CSV a mano"]
    metrics = _metrics(app)
    assert (metrics["Campañas habilitadas"], metrics["Tipos"]) == ("2", "Auto, Exact")
    assert "Funnel completo detectado (Auto + Exact presentes)." in text
    assert "Del último listado de Sponsored Products de la cuenta" in text


def test_an_account_not_listed_yet_offers_the_campaign_csv_and_scores_the_structure_neutral(monkeypatch):
    app = _generate(_page(monkeypatch, _FakeRest(listing=[])))

    text = _text(app)
    assert "Sin listar" in text and "Todavía no se listaron las campañas" in text
    assert insights_campaign_source.FILE_FALLBACK_HINT in text
    assert "Campañas habilitadas" not in _metrics(app)
    assert "Todavía no se listaron las campañas" in " ".join(str(element.value) for element in app.info)


def test_a_listing_amazon_refused_says_so(monkeypatch):
    listing = [row for row in LISTING if row["entity"] != "product_ad"]
    app = _page(monkeypatch, _FakeRest(listing, jobs=[completed_job(SP_PRODUCT_ADS_KIND, warning="sin permiso")]))

    text = _text(app)
    assert "Sin permiso" in text and "rechazó el listado de los anuncios" in text


def test_a_listing_that_cannot_be_read_says_so_and_leaves_the_file(monkeypatch):
    app = _page(monkeypatch, _FakeRest(fail_listing=True))

    assert "No se pudo leer" in _text(app)
    assert search_term_source.ASK_AN_ADMIN in " ".join(str(element.value) for element in app.error)


def test_a_campaign_csv_by_hand_replaces_the_listing_on_the_cards(monkeypatch):
    csv = pd.DataFrame({"Campaign Name": [f"Luna - {HERO} - SP - KW - BROAD"], "State": ["enabled"]})
    upload = _Upload("campaigns.csv", csv.to_csv(index=False).encode("utf-8"))
    app = _page(monkeypatch, _FakeRest(), uploads={insights_campaign_source.UPLOADER_KEY: upload})

    app.button(key="insights_campaigns_src_upload_manual").click().run()
    _generate(app)

    text = _text(app)
    assert insights_campaign_source.FILE_MODE_NOTE in text
    assert [button.label for button in app.button if button.key.startswith("insights_campaigns")] == [
        "Volver a datos de Amazon Ads"]
    metrics = _metrics(app)
    assert (metrics["Campañas habilitadas"], metrics["Tipos"]) == ("1", "Broad")
    assert "Del Campaign CSV subido a mano" in text

    app.button(key="insights_campaigns_src_back_to_api").click().run()
    _generate(app)
    assert _metrics(app)["Tipos"] == "Auto, Exact"


def test_the_campaigns_input_signature_follows_the_listing_time_or_the_file():
    listing = insights_campaign_source.CampaignsInput(
        listing=insights_campaign_source.ListedCampaigns(pd.DataFrame(), datetime(2026, 9, 29, tzinfo=timezone.utc)))
    first = insights_campaign_source.CampaignsInput(upload=_Upload("a.csv", b"a"))

    assert listing.signature == "listing:2026-09-29T00:00:00+00:00"
    assert first.signature != insights_campaign_source.CampaignsInput(upload=_Upload("a.csv", b"b")).signature
    assert insights_campaign_source.CampaignsInput().signature == ""

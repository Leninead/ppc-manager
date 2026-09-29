"""The «Estado de campaña» filter the pages mount (modules/pages/campaign_status_filter.py), in AppTest."""
from streamlit.testing.v1 import AppTest

from core.amazon_ads.campaign_status import StatusFilter
from core.search_term.frame import SOURCE_API, SOURCE_FILE
from core.ui import i18n

# Search terms of four campaigns, with the state the synced report gives each one.
_SEARCH_TERMS_SCRIPT = """
import pandas as pd
import streamlit as st
from core.search_term.frame import SearchTermSource
from modules.pages.campaign_status_filter import filter_search_terms_by_status

source = SearchTermSource(frame=None, source=st.session_state["test_source_kind"], currency_code="USD", label="Demo",
                          signature="demo", attribution_days=7, bulk_ready=False)
terms = pd.DataFrame({"Customer Search Term": ["kids shoes", "shoe rack", "old shoes", "red shoes"],
                      "_campaign_status": ["ENABLED", "PAUSED", "ARCHIVED", "enabled"]})
# A period without search terms: the page returns before drawing the filter.
if not st.session_state.get("test_without_terms"):
    shown = filter_search_terms_by_status(source, terms, key="demo_status")
    st.session_state["test_shown"] = list(shown["Customer Search Term"])
"""


def _run(source_kind=SOURCE_API, language="Español") -> AppTest:
    app = AppTest.from_string(_SEARCH_TERMS_SCRIPT, default_timeout=30)
    app.session_state["test_source_kind"] = source_kind
    app.session_state["app_lang"] = language
    app.run()
    assert not app.exception
    return app


def _shown(app: AppTest) -> list[str]:
    return app.session_state["test_shown"]


def test_it_opens_on_the_active_campaigns():
    app = _run()

    assert app.selectbox(key="demo_status").label == "Estado de campaña"
    assert app.selectbox(key="demo_status").value == StatusFilter.ENABLED
    assert _shown(app) == ["kids shoes", "red shoes"]


def test_choosing_paused_leaves_only_the_terms_of_paused_campaigns():
    app = _run()

    app.selectbox(key="demo_status").set_value(StatusFilter.PAUSED).run()

    assert _shown(app) == ["shoe rack"]


def test_all_keeps_the_archived_campaigns_and_all_but_archived_leaves_them_out():
    app = _run()

    app.selectbox(key="demo_status").set_value(StatusFilter.ALL).run()
    assert _shown(app) == ["kids shoes", "shoe rack", "old shoes", "red shoes"]

    app.selectbox(key="demo_status").set_value(StatusFilter.ALL_BUT_ARCHIVED).run()
    assert _shown(app) == ["kids shoes", "shoe rack", "red shoes"]


def test_the_choice_stays_on_the_next_run():
    app = _run()
    app.selectbox(key="demo_status").set_value(StatusFilter.ARCHIVED).run()

    app.run()

    assert app.selectbox(key="demo_status").value == StatusFilter.ARCHIVED
    assert _shown(app) == ["old shoes"]


def test_the_choice_survives_a_run_that_does_not_draw_the_filter():
    app = _run()
    app.selectbox(key="demo_status").set_value(StatusFilter.PAUSED).run()

    app.session_state["test_without_terms"] = True
    app.run()
    app.session_state["test_without_terms"] = False
    app.run()

    assert app.selectbox(key="demo_status").value == StatusFilter.PAUSED
    assert _shown(app) == ["shoe rack"]


def test_a_hand_uploaded_report_keeps_every_term_and_says_why():
    app = _run(SOURCE_FILE)

    assert _shown(app) == ["kids shoes", "shoe rack", "old shoes", "red shoes"]
    assert app.selectbox[0].disabled
    assert "El archivo subido a mano no trae el estado de las campañas: se muestran todas." in [
        caption.value for caption in app.caption]


def test_in_english_it_reads_like_campaign_managers_filter_and_keeps_the_same_campaigns():
    app = _run(language="English")

    selectbox = app.selectbox(key="demo_status")
    assert selectbox.label == "Active status"
    assert selectbox.options == ["All", "All but archived", "Enabled", "Paused", "Archived"]
    assert selectbox.value == StatusFilter.ENABLED
    assert _shown(app) == ["kids shoes", "red shoes"]


def test_switching_the_language_keeps_the_chosen_status():
    app = _run()
    app.selectbox(key="demo_status").set_value(StatusFilter.PAUSED).run()

    app.session_state["app_lang"] = "English"
    app.run()

    assert app.selectbox(key="demo_status").options[2] == "Enabled"
    assert app.selectbox(key="demo_status").value == StatusFilter.PAUSED
    assert _shown(app) == ["shoe rack"]


def test_a_hand_uploaded_report_says_why_in_english_too():
    app = _run(SOURCE_FILE, language="English")

    assert "A hand-uploaded report carries no campaign status: every campaign is shown." in [
        caption.value for caption in app.caption]


def test_every_text_of_the_filter_has_both_languages():
    namespaces = ("campaign_status.", "bulk_campaigns.")
    spanish = {key for key in i18n._ES if key.startswith(namespaces)}
    english = {key for key in i18n._EN if key.startswith(namespaces)}

    assert spanish == english
    assert {f"campaign_status.option.{status.value}" for status in StatusFilter} <= spanish

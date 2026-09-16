"""The SQP page and the app chat: it renders on every file and never leaves a stale analysis behind."""
import io
import time

import pandas as pd
from streamlit.testing.v1 import AppTest

import ai.client as ai_client
import ai.runtime as ai_runtime
from modules.pages import search_query_performance as sqp_page

# Two rows of a real Brand Analytics export (Wamery, week 35 of 2026).
_EXPORT = '''"Search Query","Search Query Score","Search Query Volume","Impressions: Total Count","Impressions: Brand Count","Impressions: Brand Share %","Clicks: Total Count","Clicks: Click Rate %","Clicks: Brand Count","Clicks: Brand Share %","Clicks: Price (Median)","Clicks: Brand Price (Median)","Clicks: Same Day Shipping Speed","Clicks: 1D Shipping Speed","Clicks: 2D Shipping Speed","Cart Adds: Total Count","Cart Adds: Cart Add Rate %","Cart Adds: Brand Count","Cart Adds: Brand Share %","Cart Adds: Price (Median)","Cart Adds: Brand Price (Median)","Cart Adds: Same Day Shipping Speed","Cart Adds: 1D Shipping Speed","Cart Adds: 2D Shipping Speed","Purchases: Total Count","Purchases: Purchase Rate %","Purchases: Brand Count","Purchases: Brand Share %","Purchases: Price (Median)","Purchases: Brand Price (Median)","Purchases: Same Day Shipping Speed","Purchases: 1D Shipping Speed","Purchases: 2D Shipping Speed","Reporting Date"
"brita bottle filter replacement","843","266","8405","8","0.1","91","34.21","0","0.0","11.97",,"4","51","19","59","22.18","0","0.0","11.97",,"3","35","13","30","11.28","0","0.0","11.97",,"2","22","3","2026-08-29"
"cold steel","898","14874","381915","7","0.0","4324","29.07","0","0.0","47.09",,"147","1126","966","653","4.39","0","0.0","36.99",,"21","172","141","67","0.45","0","0.0","27.68",,"4","33","14","2026-08-29"
'''

_SCRIPT = """
import streamlit as st
from core import app_chat
from modules.pages import search_query_performance
if st.session_state.get("shared_before"):
    app_chat.report_failed("sqp")
search_query_performance.render()
"""


def _page_with_file(monkeypatch, frame):
    import streamlit
    uploaded = type("Uploaded", (), {"name": "sqp.csv", "getvalue": lambda self: b"sqp", "seek": lambda self, n: None})()
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: uploaded)
    monkeypatch.setattr(sqp_page, "read_sqp", lambda file: frame.copy())
    monkeypatch.setattr(sqp_page, "extract_sqp_brand", lambda file: "luna")
    return AppTest.from_string(_SCRIPT, default_timeout=60)


def test_a_file_without_brand_impressions_renders_and_withdraws_the_sqp_analysis(monkeypatch):
    frame = pd.DataFrame({"Search Query": ["luna pajamas", "kids pajamas"],
                          "Search Query Volume": [1200, 800],
                          "Impressions: Total Count": [50000, 30000]})
    app = _page_with_file(monkeypatch, frame)
    app.session_state["shared_before"] = True

    app.run()

    assert not app.exception
    assert "sqp" not in app.session_state["app_chat_modules"]


def test_a_finished_analysis_reaches_the_chat_with_its_documents_and_the_query_behind_each_row(monkeypatch):
    frame = pd.read_csv(io.StringIO(_EXPORT))
    answer = {"synthesis": {"situation": "La marca casi no aparece.", "week_actions": ["Exponer Q01"],
                            "mid_term": [], "risks": [], "executive_summary": "2 queries."},
              "queries": [{"row_id": "Q01", "query_type": "GENERICA", "funnel_diagnosis": "SIN_VISIBILIDAD",
                           "price_causality": "INDETERMINADO", "action": "AGREGAR_EXACT", "confidence": "MEDIA",
                           "reasoning": "el mercado compra 67 veces", "warning": None}]}
    monkeypatch.setattr(ai_client, "ask", lambda **call: {"structured_output": answer, "session_id": "sqp-session"})
    with ai_runtime._lock:
        ai_runtime._registry.clear()
    app = _page_with_file(monkeypatch, frame)

    app.run()
    for _ in range(30):
        entry = app.session_state["app_chat_modules"].get("sqp")
        if entry is not None and entry.state == "current":
            break
        time.sleep(0.2)
        app.run()

    assert not app.exception
    shared = app.session_state["app_chat_modules"]["sqp"].analysis
    titles = [document["title"] for document in shared.documents]
    assert titles[0] == "Search Query Performance · marca luna · semana 2026-08-29 · Parámetros"
    assert titles[-1] == "Search Query Performance · marca luna · semana 2026-08-29 · Lectura de la IA"
    assert ("Q01 · cold steel → GENERICA · SIN_VISIBILIDAD · INDETERMINADO · AGREGAR_EXACT · MEDIA: "
            "el mercado compra 67 veces") in shared.documents[-1]["content"]
    assert shared.annotate("Exponer Q01 por su imp_share") == "Exponer Q01 (cold steel) por su share de impresiones"
    with ai_runtime._lock:
        ai_runtime._registry.clear()


def test_without_a_file_the_page_withdraws_the_sqp_analysis(monkeypatch):
    import streamlit
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: None)
    app = AppTest.from_string(_SCRIPT, default_timeout=60)
    app.session_state["shared_before"] = True

    app.run()

    assert not app.exception
    assert "sqp" not in app.session_state["app_chat_modules"]

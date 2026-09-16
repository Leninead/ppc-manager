"""The DataDive page and the app chat: a finished analysis reaches it with the keyword behind each row id."""
import time

import pandas as pd
from streamlit.testing.v1 import AppTest

import ai.client as ai_client
import ai.runtime as ai_runtime
from modules.pages import datadive_analyzer as dd_page

_SCRIPT = """
from modules.pages import datadive_analyzer
datadive_analyzer.render()
"""

_ANSWER = {"clusters": [{"nombre": "Núcleo genérico", "racional": "Cabeza del niche.", "row_ids": ["K01", "K02"],
                         "match_type": "exact", "prioridad": "alta"}],
           "gaps": [{"row_id": "K02", "razon": "el ASIN no aparece", "via": "PPC_AHORA", "confianza": "alta",
                     "advertencia": None}],
           "synthesis": {"situation": "El niche lo domina un competidor.", "week_actions": ["Abrir K01"],
                         "mid_term": [], "risks": [], "executive_summary": "3 keywords."}}


def _mkl_frame():
    return pd.DataFrame({
        "Search Term": ["collagen powder", "collagen peptides", "marine collagen"],
        "SV": [120000, 45000, 9000],
        "Relevance": [8.4, 6.1, 3.2],
        "Sugg. Bid": [1.85, 1.2, 0.9],
        "Launch Score": [320.0, 210.0, 40.0],
        "B00COMP1": [3, 8, 14],
        "B00COMP2": [5, 12, 21],
    })


def test_a_finished_mkl_analysis_reaches_the_chat_with_the_keyword_behind_each_row_id(monkeypatch):
    import streamlit
    uploaded = type("Uploaded", (), {"name": "niche-collagen-keywords.xlsx",
                                     "getvalue": lambda self: b"mkl"})()
    monkeypatch.setattr(streamlit, "file_uploader", lambda *args, **kwargs: uploaded)
    # Without a DataDive key the tab has no API mode and reads the uploaded export.
    monkeypatch.setattr(dd_page.dd_api, "client_from_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(dd_page, "_parse_mkl", lambda data, name: (_mkl_frame(), ["B00COMP1", "B00COMP2"]))
    monkeypatch.setattr(ai_client, "ask", lambda **call: {"structured_output": _ANSWER, "session_id": "dd-session"})
    with ai_runtime._lock:
        ai_runtime._registry.clear()
    app = AppTest.from_string(_SCRIPT, default_timeout=60)

    app.run()
    for _ in range(30):
        entry = app.session_state["app_chat_modules"].get("datadive")
        if entry is not None and entry.state == "current":
            break
        time.sleep(0.2)
        app.run()

    assert not app.exception
    shared = app.session_state["app_chat_modules"]["datadive"].analysis
    titles = [document["title"] for document in shared.documents]
    assert titles[0] == "DataDive · niche-collagen-keywords.xlsx · Parámetros"
    assert titles[-1] == "DataDive · niche-collagen-keywords.xlsx · Lectura de la IA"
    reading = shared.documents[-1]["content"]
    assert ("1. Núcleo genérico · prioridad alta · exact · 2 keywords, SV 165,000: Cabeza del niche. "
            "Keywords: K01 (collagen powder), K02 (collagen peptides)") in reading
    assert "K02 · collagen peptides → PPC_AHORA · alta: el ASIN no aparece" in reading
    assert shared.annotate("Abrir K01") == "Abrir K01 (collagen powder)"
    with ai_runtime._lock:
        ai_runtime._registry.clear()

"""Borrar un mes del histórico de Monthly Forecast sin perder el Spend y las
Ventas PPC manuales del resto de los meses.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from modules.pages import revenue_forecast as rf

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _history() -> list[dict]:
    return [
        {"date": "2026-01-01", "revenue": 1000.0, "units": 10.0, "sessions": 300.0,
         "cvr": 3.3, "spend": 100.0, "ventasPPC": 250.0},
        {"date": "2026-02-01", "revenue": 1100.0, "units": 11.0, "sessions": 310.0,
         "cvr": 3.5, "spend": 200.0, "ventasPPC": None},
        {"date": "2026-03-01", "revenue": 400.0, "units": 4.0, "sessions": 120.0,
         "cvr": 3.3, "spend": None, "ventasPPC": None},
    ]


def _client() -> dict:
    c = rf._new_client(name="Acme", client_id="acme")
    c["historical"] = _history()
    return c


# ─────────────────────────────────────────────────────────────────────────────
# _delete_historical_month — función pura
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_month_keeps_the_other_months_and_their_manual_ads():
    c = _client()
    assert rf._delete_historical_month(c, "2026-03-01") is True
    assert c["historical"] == _history()[:2]


def test_delete_middle_month_keeps_both_neighbours():
    c = _client()
    assert rf._delete_historical_month(c, "2026-02-01") is True
    assert [r["date"] for r in c["historical"]] == ["2026-01-01", "2026-03-01"]
    assert c["historical"][0]["spend"] == 100.0
    assert c["historical"][0]["ventasPPC"] == 250.0


def test_delete_missing_month_touches_nothing():
    c = _client()
    before = copy.deepcopy(c)
    assert rf._delete_historical_month(c, "2025-12-01") is False
    assert rf._delete_historical_month(c, "not-a-date") is False
    assert c == before


def test_delete_month_accepts_year_month():
    c = _client()
    assert rf._delete_historical_month(c, "2026-01") is True
    assert [r["date"] for r in c["historical"]] == ["2026-02-01", "2026-03-01"]


def test_delete_month_leaves_the_actual_layer_alone():
    c = _client()
    c["actual"] = [{"date": "2026-03-01", "revenue": 900.0}]
    rf._delete_historical_month(c, "2026-03-01")
    assert c["actual"] == [{"date": "2026-03-01", "revenue": 900.0}]


# ─────────────────────────────────────────────────────────────────────────────
# Popover "🗑️ Limpiar histórico" (AppTest)
# ─────────────────────────────────────────────────────────────────────────────

_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

if rf._K_CLIENTS not in st.session_state:
    c = rf._new_client(name="Acme", client_id="acme")
    c["historical"] = __HISTORY__
    st.session_state[rf._K_CLIENTS] = [c]
    st.session_state[rf._K_ACTIVE_CLIENT_ID] = "acme"
cur = rf._cur_client()
rf._render_upload_and_demo(cur)
rf._render_history_table(cur)
"""

_EDITOR_KEY = "rf_history_editor_acme"


def _positional_data_editor(df, key=None, **_kwargs):
    """Doble de st.data_editor: aplica `edited_rows` por POSICIÓN de fila, como Streamlit."""
    import streamlit as st

    out = df.copy()
    for pos, changes in (st.session_state.get(key) or {}).get("edited_rows", {}).items():
        for col, value in changes.items():
            out.at[int(pos), col] = value
    return out


@pytest.fixture
def persisted(monkeypatch):
    calls: list[int] = []
    # AppTest runs in-process: patch through monkeypatch so nothing leaks into later tests.
    monkeypatch.setattr(rf, "_try_persist", lambda *a, **k: calls.append(1) or True)
    return calls


def _app(history=None) -> AppTest:
    script = (_APP.replace("__REPO_ROOT__", str(_REPO_ROOT))
              .replace("__HISTORY__", repr(history or _history())))
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _hist(at: AppTest) -> list[dict]:
    return at.session_state[rf._K_CLIENTS][0]["historical"]


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def test_whole_history_option_is_the_default_and_unchanged(persisted):
    at = _app()
    radio = at.radio[0]
    assert list(radio.options) == ["Todo el histórico", "Un mes"]
    assert radio.value == "Todo el histórico"
    _button(at, "Sí, vaciar histórico").click().run()
    assert not at.exception
    assert _hist(at) == []


def test_one_month_option_lists_newest_first_and_warns_about_manual_ads(persisted):
    at = _app()
    at.radio[0].set_value("Un mes").run()
    month = at.selectbox[0]
    assert list(month.options) == ["Marzo 2026", "Febrero 2026", "Enero 2026"]
    assert month.value == "2026-03-01"
    assert any("Sí, borrar Marzo 2026" == b.label for b in at.button)
    assert not any(b.label == "Sí, vaciar histórico" for b in at.button)
    text = " ".join(m.value for m in at.markdown)
    assert "Marzo 2026" in text and "no tiene Spend ni Ventas PPC" in text

    month.set_value("2026-01-01").run()
    text = " ".join(m.value for m in at.markdown)
    assert "Enero 2026" in text and "Spend y Ventas PPC" in text and "se pierden" in text


def test_deleting_one_month_keeps_the_rest_persists_and_asks_to_regenerate(persisted):
    at = _app()
    at.radio[0].set_value("Un mes").run()
    _button(at, "Sí, borrar Marzo 2026").click().run()
    assert not at.exception
    assert _hist(at) == _history()[:2]
    assert persisted
    assert any("El forecast no se recalcula solo: volvé a generarlo." in w.value
               for w in at.warning)


def test_after_deleting_a_month_a_pending_edit_does_not_land_on_another_month(
        monkeypatch, persisted):
    import streamlit

    monkeypatch.setattr(streamlit, "data_editor", _positional_data_editor)
    script = (_APP.replace("__REPO_ROOT__", str(_REPO_ROOT))
              .replace("__HISTORY__", repr(_history())))
    at = AppTest.from_string(script, default_timeout=60)
    # The AM typed Spend 300 in the top row (Marzo, the newest month).
    at.session_state[_EDITOR_KEY] = {"edited_rows": {0: {"Spend": 300.0}},
                                     "added_rows": [], "deleted_rows": []}
    at.run()
    assert not at.exception
    assert _hist(at)[2]["spend"] == 300.0

    at.radio[0].set_value("Un mes").run()
    _button(at, "Sí, borrar Marzo 2026").click().run()
    assert not at.exception

    feb = next(r for r in _hist(at) if r["date"] == "2026-02-01")
    assert feb["spend"] == 200.0
    assert [r["date"] for r in _hist(at)] == ["2026-01-01", "2026-02-01"]

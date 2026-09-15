"""Tests B1a — editor de Spend / Ventas PPC sobre la capa `actual` de M31.

Espejo de lo que ya existe para `historical` (`_build_history_df`,
`_update_historical_row`, `_apply_history_edits`). La capa `actual` hasta acá
no tenía editor: sus filas quedaban con spend=None y ventasPPC=None para
siempre, así que el cumplimiento del mes en curso no se podía medir en ACOS ni
TACOS.

El test que importa es el de aislamiento: editar `actual` NO puede tocar
`historical`. Las dos capas comparten shape y un mes cerrado vive en ambas; un
helper que apunte a la lista equivocada pisaría el spend que el AM ya cargó.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from modules.pages import revenue_forecast as rf


_COLS = [
    "_idx", "Mes", "Revenue", "Units", "Sessions", "CVR%", "AOV",
    "Spend", "Ventas PPC", "ACOS%", "TACOS%",
]


def _row(date: str, revenue: float = 1000.0, units: float = 50.0,
         spend=None, ventas_ppc=None, partial=None, days_covered=None) -> dict:
    return {
        "date": date,
        "revenue": revenue,
        "units": units,
        "sessions": 500,
        "cvr": 10.0,
        "buyBox": 95.0,
        "spend": spend,
        "ventasPPC": ventas_ppc,
        "partial": partial,
        "days_covered": days_covered,
    }


def _state_with(actual: list, historical: list | None = None) -> dict:
    client = rf._new_client(name="Test", client_id="t1")
    client["actual"] = actual
    client["historical"] = historical if historical is not None else []
    return {
        rf._K_CLIENTS: [client],
        rf._K_ACTIVE_CLIENT_ID: "t1",
        rf._K_ACCOUNT_MANAGERS: [],
    }


def _client(state: dict) -> dict:
    return state[rf._K_CLIENTS][0]


# ─────────────────────────────────────────────────────────────────────────────
# _build_actual_df
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildActualDf:
    def test_lista_vacia_devuelve_columnas_correctas(self):
        df = rf._build_actual_df([])
        assert df.empty
        assert list(df.columns) == _COLS

    def test_columnas_en_el_mismo_orden_que_el_historico(self):
        df = rf._build_actual_df([_row("2026-07-01", spend=100.0, ventas_ppc=400.0)])
        assert list(df.columns) == _COLS

    def test_acos_y_tacos_calculados(self):
        df = rf._build_actual_df([_row("2026-07-01", revenue=2000.0,
                                       spend=100.0, ventas_ppc=400.0)])
        r = df.iloc[0]
        assert r["ACOS%"] == 25.0      # 100 / 400 * 100
        assert r["TACOS%"] == 5.0      # 100 / 2000 * 100

    def test_acos_none_cuando_ventas_ppc_es_cero(self):
        df = rf._build_actual_df([_row("2026-07-01", spend=100.0, ventas_ppc=0.0)])
        assert pd.isna(df.iloc[0]["ACOS%"])
        assert df.iloc[0]["TACOS%"] == 10.0

    def test_tacos_none_cuando_revenue_es_cero(self):
        df = rf._build_actual_df([_row("2026-07-01", revenue=0.0,
                                       spend=100.0, ventas_ppc=400.0)])
        assert pd.isna(df.iloc[0]["TACOS%"])
        assert df.iloc[0]["ACOS%"] == 25.0

    def test_spend_y_ventas_ppc_none_salen_como_nan(self):
        df = rf._build_actual_df([_row("2026-07-01")])
        assert pd.isna(df.iloc[0]["Spend"])
        assert pd.isna(df.iloc[0]["Ventas PPC"])
        assert pd.isna(df.iloc[0]["ACOS%"])
        assert pd.isna(df.iloc[0]["TACOS%"])

    def test_spend_y_ventas_ppc_son_float64_no_object(self):
        """Pin de dtype de Spend / Ventas PPC.

        Ojo con la causa: object NO congela el editor. Streamlit 1.43.2
        deshabilita las columnas que `is_colum_type_arrow_incompatible`
        (streamlit/dataframe_util.py:1036) marca incompatibles, y a una columna
        object le pregunta a pandas qué contiene vía `infer_dtype`. Lo que rompe
        es MEZCLAR float y '' (bug G1): eso da "mixed" y la columna queda
        deshabilitada, sin error visible. Este test fija float64 para no
        depender de la inferencia; el efecto real sobre el editor lo cubre
        `test_render_actual_table_spend_editable_con_todo_none`.
        """
        df = rf._build_actual_df([
            _row("2026-06-01", spend=None, ventas_ppc=None),
            _row("2026-07-01", spend=120.5, ventas_ppc=480.0),
        ])
        assert df["Spend"].dtype == "float64"
        assert df["Ventas PPC"].dtype == "float64"

    def test_spend_y_ventas_ppc_float64_aun_todo_none(self):
        df = rf._build_actual_df([_row("2026-07-01"), _row("2026-08-01")])
        assert df["Spend"].dtype == "float64"
        assert df["Ventas PPC"].dtype == "float64"

    def test_mes_parcial_con_dias(self):
        df = rf._build_actual_df([_row("2026-07-01", partial=True, days_covered=12)])
        assert df.iloc[0]["Mes"] == "Julio 2026 (parcial · 12 d)"

    def test_mes_parcial_sin_dias(self):
        df = rf._build_actual_df([_row("2026-07-01", partial=True, days_covered=None)])
        assert df.iloc[0]["Mes"] == "Julio 2026 (parcial)"

    def test_mes_no_parcial(self):
        df_false = rf._build_actual_df([_row("2026-07-01", partial=False, days_covered=31)])
        df_none = rf._build_actual_df([_row("2026-07-01", partial=None)])
        assert df_false.iloc[0]["Mes"] == "Julio 2026"
        assert df_none.iloc[0]["Mes"] == "Julio 2026"

    def test_idx_apunta_a_la_lista_cruda_con_orden_desc(self):
        actual = [_row("2026-06-01", spend=1.0), _row("2026-07-01", spend=2.0)]
        df = rf._build_actual_df(actual)
        # Más nuevo arriba, igual que el histórico.
        assert list(df["Mes"]) == ["Julio 2026", "Junio 2026"]
        for _, r in df.iterrows():
            assert actual[int(r["_idx"])]["spend"] == r["Spend"]


# ─────────────────────────────────────────────────────────────────────────────
# _update_actual_row
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateActualRow:
    def test_escribe_en_actual_y_deja_historical_intacto(self):
        historical = [
            _row("2026-06-01", spend=90.0, ventas_ppc=300.0),
            _row("2026-07-01", spend=110.0, ventas_ppc=420.0),
        ]
        actual = [_row("2026-07-01", partial=True, days_covered=12)]
        state = _state_with(actual, historical)
        hist_before = copy.deepcopy(_client(state)["historical"])

        assert rf._update_actual_row(0, "spend", 55.5, state=state) is True
        assert rf._update_actual_row(0, "ventasPPC", 200.0, state=state) is True

        c = _client(state)
        assert c["actual"][0]["spend"] == 55.5
        assert c["actual"][0]["ventasPPC"] == 200.0
        # Mismo mes (2026-07) en ambas capas: historical no se movió.
        assert c["historical"] == hist_before

    def test_string_vacio_normaliza_a_none(self):
        state = _state_with([_row("2026-07-01", spend=10.0)])
        assert rf._update_actual_row(0, "spend", "", state=state) is True
        assert _client(state)["actual"][0]["spend"] is None

    def test_nan_normaliza_a_none(self):
        state = _state_with([_row("2026-07-01", spend=10.0)])
        assert rf._update_actual_row(0, "spend", float("nan"), state=state) is True
        assert _client(state)["actual"][0]["spend"] is None

    def test_rechaza_field_invalido(self):
        state = _state_with([_row("2026-07-01")])
        before = copy.deepcopy(_client(state)["actual"])
        assert rf._update_actual_row(0, "revenue", 1.0, state=state) is False
        assert rf._update_actual_row(0, "partial", False, state=state) is False
        assert _client(state)["actual"] == before

    def test_idx_fuera_de_rango_devuelve_false(self):
        state = _state_with([_row("2026-07-01")])
        before = copy.deepcopy(_client(state)["actual"])
        assert rf._update_actual_row(5, "spend", 1.0, state=state) is False
        assert rf._update_actual_row(-1, "spend", 1.0, state=state) is False
        assert _client(state)["actual"] == before

    def test_sin_cliente_activo_devuelve_false(self):
        state = _state_with([_row("2026-07-01")])
        state[rf._K_ACTIVE_CLIENT_ID] = None
        assert rf._update_actual_row(0, "spend", 1.0, state=state) is False

    def test_cliente_viejo_sin_key_actual_no_rompe(self):
        state = _state_with([])
        del _client(state)["actual"]
        assert rf._update_actual_row(0, "spend", 1.0, state=state) is False


# ─────────────────────────────────────────────────────────────────────────────
# _apply_actual_edits + roundtrip
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyActualEdits:
    def test_df_vacio_devuelve_cero(self):
        state = _state_with([_row("2026-07-01")])
        assert rf._apply_actual_edits(pd.DataFrame(), state=state) == 0
        assert rf._apply_actual_edits(None, state=state) == 0

    def test_roundtrip_editar_spend_refleja_acos(self):
        actual = [
            _row("2026-06-01", revenue=3000.0, partial=False),
            _row("2026-07-01", revenue=2000.0, partial=True, days_covered=12),
        ]
        historical = [_row("2026-06-01", spend=77.0, ventas_ppc=300.0)]
        state = _state_with(actual, historical)
        hist_before = copy.deepcopy(historical)

        df = rf._build_actual_df(_client(state)["actual"])
        edited = df.copy()
        julio = edited["Mes"].str.startswith("Julio")
        edited.loc[julio, "Spend"] = 100.0
        edited.loc[julio, "Ventas PPC"] = 400.0

        written = rf._apply_actual_edits(edited, state=state)
        assert written == 2

        c = _client(state)
        assert c["actual"][1]["spend"] == 100.0
        assert c["actual"][1]["ventasPPC"] == 400.0
        # La fila no editada sigue sin dato (NaN del df → None en el state).
        assert c["actual"][0]["spend"] is None
        assert c["historical"] == hist_before

        df2 = rf._build_actual_df(c["actual"])
        r = df2[df2["Mes"].str.startswith("Julio")].iloc[0]
        assert r["ACOS%"] == 25.0
        assert r["TACOS%"] == 5.0
        assert not math.isnan(r["Spend"])


# ─────────────────────────────────────────────────────────────────────────────
# _render_actual_table — render real vía AppTest
# ─────────────────────────────────────────────────────────────────────────────
#
# El dtype float64 es la causa; esto mira el efecto. Streamlit 1.43.2 marca
# `{"disabled": true}` en la config de toda columna que considera
# Arrow-incompatible (data_editor.py:836-843), así que la config serializada en
# el proto es exactamente lo que ve el AM.

_REPO_ROOT = str(Path(__file__).resolve().parents[1])

_TABLE_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

c = rf._new_client(name="T", client_id="t1")
c["actual"] = __ACTUAL__
st.session_state[rf._K_CLIENTS] = [c]
st.session_state[rf._K_ACTIVE_CLIENT_ID] = "t1"
st.session_state[rf._K_ACCOUNT_MANAGERS] = []
rf._render_actual_table(c)
"""


def _run_table(actual: list) -> AppTest:
    script = (
        _TABLE_APP
        .replace("__REPO_ROOT__", _REPO_ROOT)
        .replace("__ACTUAL__", repr(actual))
    )
    at = AppTest.from_string(script)
    at.run()
    return at


def test_render_actual_table_spend_editable_con_todo_none():
    """El caso normal de `actual` recién subido: spend y ventasPPC en None."""
    at = _run_table([
        _row("2026-06-01", partial=False),
        _row("2026-07-01", partial=True, days_covered=12),
    ])
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"
    editors = at.get("arrow_data_frame")
    assert len(editors) == 1
    proto = editors[0].proto
    assert proto.id.endswith("rf_actual_editor_t1")
    assert not proto.disabled
    cols = json.loads(proto.columns)
    assert "disabled" not in cols["Spend"]
    assert "disabled" not in cols["Ventas PPC"]
    assert cols["ACOS%"].get("disabled") is True
    assert cols["_idx"].get("hidden") is True


def test_render_actual_table_sin_mes_real_no_dibuja_editor():
    at = _run_table([])
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"
    assert len(at.get("arrow_data_frame")) == 0
    assert any("mes real" in c.value for c in at.caption)

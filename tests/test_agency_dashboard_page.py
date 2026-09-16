"""Tests B3a-2 — pantalla del Dashboard Global (M39).

La página no calcula nada: consume `core.agency_dashboard`. Por eso los tests
mockean la capa de datos y NO tocan disco.

Los helpers de formato y de color se testean PUROS, aparte del render: son lo
que más fácil se rompe, y el del color de ACOS/TACOS tiene el signo invertido
respecto de revenue (un delta positivo es PEOR).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import agency_dashboard_format as fmt
from modules.pages import agency_dashboard_page as page


_REPO_ROOT = str(Path(__file__).resolve().parents[1])


# ─────────────────────────────────────────────────────────────────────────────
# Datos de prueba
# ─────────────────────────────────────────────────────────────────────────────

def _cell(actual=None, forecast=None, acco=None, partial=None) -> dict:
    keys = ("revenue", "ventasPPC", "spend", "acos", "tacos")
    return {
        "actual": actual,
        "forecast": forecast,
        "accomplishment": {k: (acco or {}).get(k) for k in keys},
        "partial": partial,
    }


def _account(name="Dermaglos", client_id="derm", has_baseline=True,
             months=None, currency="USD") -> dict:
    return {
        "client_id": client_id,
        "name": name,
        "currency": currency,
        "has_baseline": has_baseline,
        "baseline_name": "Plan 2026" if has_baseline else None,
        "baseline_created_at": "2026-09-01" if has_baseline else None,
        "months": months or {},
    }


def _fake_dash(accounts, periods=("2026-08", "2026-09")) -> dict:
    return {"periods": list(periods), "accounts": accounts}


_MES_REAL = {
    "actual": {"revenue": 9000.0, "ventasPPC": 3000.0, "spend": 900.0,
               "acos": 30.0, "tacos": 10.0},
    "acco": {"revenue": 90.0, "ventasPPC": 75.0, "spend": 120.0,
             "acos": 1.0, "tacos": 2.5},
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers puros — formato
# ─────────────────────────────────────────────────────────────────────────────

class TestFmtAcco:
    def test_pct_para_revenue_ad_sales_y_spend(self):
        assert fmt._fmt_acco("revenue", 90.0) == "90.0%"
        assert fmt._fmt_acco("ventasPPC", 75.24) == "75.2%"
        assert fmt._fmt_acco("ventasPPC", 75.26) == "75.3%"
        assert fmt._fmt_acco("spend", 120.0) == "120.0%"

    def test_empate_de_redondeo_usa_el_bancario_de_python(self):
        """`format` redondea al par en los empates: 75.25 → "75.2", no "75.3".
        Se fija acá para que nadie lo lea como un bug de la tabla. Es display:
        ningún cálculo depende de este decimal."""
        assert fmt._fmt_acco("ventasPPC", 75.25) == "75.2%"

    def test_delta_con_signo_para_acos_y_tacos(self):
        assert fmt._fmt_acco("acos", 1.0) == "+1.0"
        assert fmt._fmt_acco("acos", -1.0) == "-1.0"
        assert fmt._fmt_acco("tacos", 2.5) == "+2.5"
        assert fmt._fmt_acco("tacos", 0.0) == "+0.0"

    def test_delta_no_lleva_porcentaje(self):
        assert "%" not in fmt._fmt_acco("acos", 1.0)

    def test_none_es_cadena_vacia(self):
        for metric in ("revenue", "ventasPPC", "spend", "acos", "tacos"):
            assert fmt._fmt_acco(metric, None) == ""


class TestFmtActual:
    def test_moneda_para_revenue_ad_sales_y_spend(self):
        assert fmt._fmt_actual("revenue", 9000.0, "USD") == "USD 9,000"
        assert fmt._fmt_actual("spend", 1234.56, "MXN") == "MXN 1,235"

    def test_pct_para_acos_y_tacos(self):
        assert fmt._fmt_actual("acos", 30.0, "USD") == "30.0%"
        assert fmt._fmt_actual("tacos", 9.87, "USD") == "9.9%"

    def test_none_es_cadena_vacia(self):
        assert fmt._fmt_actual("revenue", None, "USD") == ""
        assert fmt._fmt_actual("acos", None, "USD") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Helper puro — semáforo
# ─────────────────────────────────────────────────────────────────────────────

class TestAccoColor:
    def test_revenue_verde_amarillo_rojo(self):
        assert fmt._acco_color("revenue", 92.0) == fmt._VERDE
        assert fmt._acco_color("revenue", 90.0) == fmt._VERDE
        assert fmt._acco_color("revenue", 87.0) == fmt._AMARILLO
        assert fmt._acco_color("revenue", 85.0) == fmt._AMARILLO
        assert fmt._acco_color("revenue", 80.0) == fmt._ROJO

    def test_mismo_criterio_para_ad_sales_y_spend(self):
        assert fmt._acco_color("ventasPPC", 95.0) == fmt._VERDE
        assert fmt._acco_color("spend", 70.0) == fmt._ROJO

    def test_acos_signo_invertido(self):
        """EL test: en ACOS un delta POSITIVO es peor (gastó más que el plan)."""
        assert fmt._acco_color("acos", -1.0) == fmt._VERDE
        assert fmt._acco_color("acos", 0.0) == fmt._VERDE
        assert fmt._acco_color("acos", 1.0) == fmt._AMARILLO
        assert fmt._acco_color("acos", 2.0) == fmt._AMARILLO
        assert fmt._acco_color("acos", 3.0) == fmt._ROJO
        # Un +1 en ACOS NO se puede leer con la regla de revenue.
        assert fmt._acco_color("acos", 1.0) != fmt._acco_color("revenue", 1.0)

    def test_tacos_mismo_criterio_que_acos(self):
        assert fmt._acco_color("tacos", -0.5) == fmt._VERDE
        assert fmt._acco_color("tacos", 2.0) == fmt._AMARILLO
        assert fmt._acco_color("tacos", 2.1) == fmt._ROJO

    def test_delta_bajo_la_resolucion_de_la_celda_es_verde(self):
        """EL test del bug que encontró el smoke de M39: un delta de +1.3e-06
        se muestra como "+0.0" (la celda tiene 1 decimal) y se pintaba AMARILLO.
        Una cuenta clavada en el target no puede salir como advertencia."""
        assert fmt._acco_color("acos", 0.00001) == fmt._VERDE
        assert fmt._acco_color("tacos", 1.3e-06) == fmt._VERDE

    def test_bordes_del_epsilon(self):
        assert fmt._acco_color("acos", 0.05) == fmt._VERDE      # borde inferior
        assert fmt._acco_color("acos", 0.06) == fmt._AMARILLO   # un paso más

    def test_el_epsilon_no_toca_el_regimen_de_porcentaje(self):
        """El epsilon es SOLO para el delta en puntos. Revenue sigue igual."""
        assert fmt._acco_color("revenue", 92.0) == fmt._VERDE
        assert fmt._acco_color("revenue", 87.0) == fmt._AMARILLO
        assert fmt._acco_color("revenue", 78.0) == fmt._ROJO
        assert fmt._acco_color("spend", 0.05) == fmt._ROJO      # 0,05% de plan

    def test_none_sin_color(self):
        assert fmt._acco_color("revenue", None) == ""
        assert fmt._acco_color("acos", None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers puros — ventana y etiquetas de mes
# ─────────────────────────────────────────────────────────────────────────────

class TestPeriods:
    def test_ventana_default_2_atras_3_adelante(self):
        from datetime import date
        periods = fmt._build_periods(2, 3, hoy=date(2026, 9, 15))
        assert periods == ["2026-07", "2026-08", "2026-09", "2026-10",
                           "2026-11", "2026-12"]

    def test_ventana_cruza_anios(self):
        from datetime import date
        periods = fmt._build_periods(2, 1, hoy=date(2026, 1, 10))
        assert periods == ["2025-11", "2025-12", "2026-01", "2026-02"]

    def test_ventana_minima_solo_mes_actual(self):
        from datetime import date
        assert fmt._build_periods(0, 0, hoy=date(2026, 9, 1)) == ["2026-09"]

    def test_label_mes_abreviado_en_espaniol(self):
        assert fmt._month_label("2026-08", with_year=False) == "Ago"
        assert fmt._month_label("2026-12", with_year=False) == "Dic"

    def test_label_con_anio_cuando_la_ventana_cruza_anios(self):
        assert fmt._month_label("2026-01", with_year=True) == "Ene 26"


# ─────────────────────────────────────────────────────────────────────────────
# DataFrame de display
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountDf:
    def _acc(self):
        return _account(months={
            "2026-08": _cell(actual=_MES_REAL["actual"], acco=_MES_REAL["acco"],
                             partial=False),
            "2026-09": _cell(actual={"revenue": 4000.0, "ventasPPC": None,
                                     "spend": 400.0, "acos": None, "tacos": 10.0},
                             acco={"revenue": 40.0}, partial=True),
            "2026-10": _cell(),   # futuro: todo None
        })

    def test_filas_en_el_orden_del_mockup(self):
        df, _ = fmt._account_df(self._acc(), ["2026-08", "2026-09", "2026-10"])
        assert list(df.index) == ["Revenue", "Ad Sales", "Ad Spend", "ACOS", "TACOS"]

    def test_columnas_aplanadas_actual_y_acco_por_mes(self):
        df, _ = fmt._account_df(self._acc(), ["2026-08", "2026-09", "2026-10"])
        assert list(df.columns) == [
            "Ago Actual", "Ago Acco",
            "Sep* Actual", "Sep* Acco",
            "Oct Actual", "Oct Acco",
        ]

    def test_valores_formateados(self):
        df, _ = fmt._account_df(self._acc(), ["2026-08", "2026-09"])
        assert df.loc["Revenue", "Ago Actual"] == "USD 9,000"
        assert df.loc["Revenue", "Ago Acco"] == "90.0%"
        assert df.loc["ACOS", "Ago Actual"] == "30.0%"
        assert df.loc["ACOS", "Ago Acco"] == "+1.0"

    def test_mes_futuro_queda_vacio_pero_con_columnas(self):
        df, _ = fmt._account_df(self._acc(), ["2026-08", "2026-10"])
        assert (df["Oct Actual"] == "").all()
        assert (df["Oct Acco"] == "").all()

    def test_metrica_sin_dato_queda_vacia(self):
        df, _ = fmt._account_df(self._acc(), ["2026-09"])
        assert df.loc["Ad Sales", "Sep* Actual"] == ""
        assert df.loc["ACOS", "Sep* Actual"] == ""
        assert df.loc["ACOS", "Sep* Acco"] == ""

    def test_ningun_none_crudo_en_el_df(self):
        """Arrow-safe: todas las celdas son str antes de llegar a st.dataframe."""
        df, _ = fmt._account_df(self._acc(), ["2026-08", "2026-09", "2026-10"])
        assert not df.isna().any().any()
        assert all(isinstance(v, str) for v in df.to_numpy().ravel())

    def test_marca_de_parcial_en_el_mes_y_en_el_flag(self):
        df, hay_parcial = fmt._account_df(self._acc(), ["2026-08", "2026-09"])
        assert hay_parcial is True
        assert any(c.startswith("Sep*") for c in df.columns)
        assert not any(c.startswith("Ago*") for c in df.columns)

    def test_sin_parcial_no_marca(self):
        acc = _account(months={"2026-08": _cell(actual=_MES_REAL["actual"],
                                                partial=False)})
        df, hay_parcial = fmt._account_df(acc, ["2026-08"])
        assert hay_parcial is False
        assert list(df.columns) == ["Ago Actual", "Ago Acco"]

    def test_cuenta_sin_baseline_tiene_acco_vacio(self):
        acc = _account(has_baseline=False, months={
            "2026-08": _cell(actual=_MES_REAL["actual"], partial=False),
        })
        df, _ = fmt._account_df(acc, ["2026-08"])
        assert df.loc["Revenue", "Ago Actual"] == "USD 9,000"
        assert (df["Ago Acco"] == "").all()

    def test_moneda_de_la_cuenta(self):
        acc = _account(currency="MXN", months={
            "2026-08": _cell(actual=_MES_REAL["actual"], partial=False)})
        df, _ = fmt._account_df(acc, ["2026-08"])
        assert df.loc["Revenue", "Ago Actual"].startswith("MXN")


# ─────────────────────────────────────────────────────────────────────────────
# render() vía AppTest — guard de rol, vacío, 2 cuentas, badge
# ─────────────────────────────────────────────────────────────────────────────

_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from core import agency_dashboard_format as fmt
from modules.pages import agency_dashboard_page as page

llamadas = []

def _fake(periods, clients=None):
    llamadas.append(periods)
    st.session_state["_llamadas"] = len(llamadas)
    return __DASH__

page._build_agency_dashboard = _fake
st.session_state["_llamadas"] = 0
page.render(username="quien", role="__ROLE__")
"""


def _run(dash_repr: str, role: str) -> AppTest:
    script = (
        _APP.replace("__REPO_ROOT__", _REPO_ROOT)
        .replace("__DASH__", dash_repr)
        .replace("__ROLE__", role)
    )
    at = AppTest.from_string(script)
    at.run()
    return at


def _texts(at: AppTest) -> str:
    out = []
    for coll in (at.markdown, at.caption, at.info, at.warning, at.error, at.success):
        out += [e.value for e in coll]
    return "\n".join(out)


def test_no_admin_no_carga_datos_y_avisa():
    """El riel esconde el botón, pero app.py renderiza igual si `selected`
    llega por otra vía. Esta pantalla muestra plata de TODAS las cuentas."""
    at = _run(repr(_fake_dash([_account()])), "usuario")
    assert not at.exception
    assert at.session_state["_llamadas"] == 0        # no se cargó nada
    assert "Dirección" in _texts(at)
    assert len(at.get("arrow_data_frame")) == 0


def test_admin_sin_cuentas_muestra_info_y_no_explota():
    at = _run(repr(_fake_dash([])), "admin")
    assert not at.exception
    assert at.session_state["_llamadas"] == 1
    assert "forecast" in _texts(at).lower()
    assert len(at.get("arrow_data_frame")) == 0


def test_admin_con_dos_cuentas_dibuja_dos_tablas():
    meses = {"2026-08": _cell(actual=_MES_REAL["actual"], acco=_MES_REAL["acco"],
                              partial=False)}
    dash = _fake_dash(
        [_account(name="Alfa", client_id="alfa", months=meses),
         _account(name="Beta", client_id="beta", months=meses)],
        periods=("2026-08",),
    )
    at = _run(repr(dash), "admin")
    assert not at.exception
    assert len(at.get("arrow_data_frame")) == 2
    textos = _texts(at)
    assert "Alfa" in textos and "Beta" in textos


def test_cuenta_sin_baseline_muestra_badge():
    dash = _fake_dash(
        [_account(name="SinPlan", has_baseline=False, months={
            "2026-08": _cell(actual=_MES_REAL["actual"], partial=False)})],
        periods=("2026-08",),
    )
    at = _run(repr(dash), "admin")
    assert not at.exception
    assert "sin plan" in _texts(at).lower()
    assert len(at.get("arrow_data_frame")) == 1


def test_nota_al_pie_de_parcial_solo_si_hay_parcial():
    con = _fake_dash([_account(months={
        "2026-09": _cell(actual=_MES_REAL["actual"], partial=True)})],
        periods=("2026-09",))
    sin = _fake_dash([_account(months={
        "2026-09": _cell(actual=_MES_REAL["actual"], partial=False)})],
        periods=("2026-09",))
    assert "MtD" in _texts(_run(repr(con), "admin"))
    assert "MtD" not in _texts(_run(repr(sin), "admin"))


# ─────────────────────────────────────────────────────────────────────────────
# Semáforo aplicado — el mapeo columna Acco → mes es la parte frágil
# ─────────────────────────────────────────────────────────────────────────────

def test_style_df_pinta_la_celda_correcta_de_cada_mes():
    """Dos meses con cumplimientos opuestos: el color tiene que caer en la
    columna del mes que corresponde, no corrido."""
    acc = _account(months={
        "2026-08": _cell(actual=_MES_REAL["actual"],
                         acco={"revenue": 95.0, "acos": -1.0}, partial=False),
        "2026-09": _cell(actual=_MES_REAL["actual"],
                         acco={"revenue": 70.0, "acos": 5.0}, partial=False),
    })
    periods = ["2026-08", "2026-09"]
    df, _ = fmt._account_df(acc, periods)
    estilos = fmt._style_df(acc, periods, df)._compute().ctx

    def _css(fila: str, col: str) -> str:
        i = list(df.index).index(fila)
        j = list(df.columns).index(col)
        return ";".join(p for pair in estilos.get((i, j), []) for p in pair)

    assert fmt._VERDE in _css("Revenue", "Ago Acco")
    assert fmt._ROJO in _css("Revenue", "Sep Acco")
    assert fmt._VERDE in _css("ACOS", "Ago Acco")     # delta -1 = mejor que el plan
    assert fmt._ROJO in _css("ACOS", "Sep Acco")      # delta +5 = peor
    # Las columnas Actual nunca se pintan.
    assert _css("Revenue", "Ago Actual") == ""
    assert _css("ACOS", "Sep Actual") == ""


def test_style_df_sin_dato_no_pinta():
    acc = _account(has_baseline=False, months={
        "2026-08": _cell(actual=_MES_REAL["actual"], partial=False)})
    periods = ["2026-08"]
    df, _ = fmt._account_df(acc, periods)
    assert fmt._style_df(acc, periods, df)._compute().ctx == {}

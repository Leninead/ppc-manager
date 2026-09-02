"""Tests de core/ppc_metrics.py — INV-7, una sola fuente de verdad del ACoS.

El invariante que se defiende acá: cuando no hay ventas, el ACoS es None, no
cero. Un cero se lee como "excelente" en cualquier semáforo, y es el peor
default posible para el caso "gastó y no vendió".

Contrato: `.claude/skills/ppc-business-invariants.md` — INV-7.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.ppc_metrics import acos_series, calc_acos, calc_ctr, calc_cvr


# ---------------------------------------------------------------------
# calc_acos
# ---------------------------------------------------------------------

def test_caso_normal():
    assert calc_acos(25, 100) == 25.0


def test_sales_cero_devuelve_none_no_cero():
    """El caso que motiva todo el helper."""
    resultado = calc_acos(80, 0)
    assert resultado is None
    assert resultado != 0, "un ACoS de 0 se leería como el término más eficiente"


def test_sales_negativo_devuelve_none():
    assert calc_acos(50, -10) is None


def test_spend_cero_con_ventas_devuelve_cero_real():
    """Cero de gasto con ventas SÍ es un ACoS de 0: es dato, no ausencia."""
    assert calc_acos(0, 100) == 0.0


@pytest.mark.parametrize("spend, sales", [
    (float("nan"), 100),
    (25, float("nan")),
    (float("nan"), float("nan")),
    (None, 100),
    (25, None),
    (None, None),
    (np.nan, 100),
    (pd.NA, 100),
])
def test_nan_o_none_en_cualquier_argumento_devuelve_none(spend, sales):
    assert calc_acos(spend, sales) is None


@pytest.mark.parametrize("spend, sales", [
    ("abc", 100),
    (25, "s/d"),
    (25, ""),
])
def test_valores_no_numericos_devuelven_none(spend, sales):
    assert calc_acos(spend, sales) is None


def test_acepta_numeros_como_string():
    assert calc_acos("25", "100") == 25.0


def test_acos_mayor_a_cien_es_valido():
    """Gastar más de lo que vendés es un ACoS real, no un error."""
    assert calc_acos(200, 100) == 200.0


# ---------------------------------------------------------------------
# calc_cvr / calc_ctr
# ---------------------------------------------------------------------

def test_calc_cvr_clicks_cero_devuelve_none():
    assert calc_cvr(0, 0) is None
    assert calc_cvr(5, 0) is None


def test_calc_cvr_caso_normal():
    assert calc_cvr(3, 30) == 10.0


def test_calc_cvr_cero_ordenes_con_clicks_es_cero_real():
    assert calc_cvr(0, 40) == 0.0


def test_calc_ctr_impresiones_cero_devuelve_none():
    assert calc_ctr(10, 0) is None


def test_calc_ctr_caso_normal():
    assert calc_ctr(5, 1000) == 0.5


# ---------------------------------------------------------------------
# acos_series
# ---------------------------------------------------------------------

def test_acos_series_pone_nan_donde_no_hubo_ventas():
    spend = pd.Series([25.0, 80.0, 10.0])
    sales = pd.Series([100.0, 0.0, 50.0])

    out = acos_series(spend, sales)

    assert out.iloc[0] == 25.0
    assert math.isnan(out.iloc[1]), "sales=0 tiene que quedar NaN, no 0"
    assert out.iloc[2] == 20.0


def test_acos_series_no_aplica_fillna():
    """Si alguien mete un fillna(0) río abajo, este test lo caza."""
    out = acos_series(pd.Series([80.0]), pd.Series([0.0]))
    assert out.isna().all()


def test_acos_series_sales_negativo_queda_nan():
    out = acos_series(pd.Series([50.0]), pd.Series([-10.0]))
    assert math.isnan(out.iloc[0])


def test_acos_series_nan_de_entrada_se_propaga():
    out = acos_series(pd.Series([np.nan, 25.0]), pd.Series([100.0, np.nan]))
    assert out.isna().all()


def test_acos_series_devuelve_float64_sin_inf():
    out = acos_series(pd.Series([25.0, 80.0]), pd.Series([100.0, 0.0]))
    assert out.dtype == "float64"
    assert not np.isinf(out.dropna()).any()


def test_acos_series_preserva_el_indice():
    spend = pd.Series([25.0, 80.0], index=["kw a", "kw b"])
    sales = pd.Series([100.0, 0.0], index=["kw a", "kw b"])

    out = acos_series(spend, sales)

    assert list(out.index) == ["kw a", "kw b"]


def test_acos_series_coincide_con_calc_acos_fila_a_fila():
    spend = pd.Series([25.0, 80.0, 0.0, 200.0])
    sales = pd.Series([100.0, 0.0, 50.0, 100.0])

    out = acos_series(spend, sales)

    for i in range(len(spend)):
        escalar = calc_acos(spend.iloc[i], sales.iloc[i])
        if escalar is None:
            assert math.isnan(out.iloc[i])
        else:
            assert out.iloc[i] == pytest.approx(escalar)

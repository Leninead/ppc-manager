"""
Metricas de PPC con una sola fuente de verdad (INV-7).

Por que existe:
  El ACoS se calculaba en cada modulo por su cuenta, y casi siempre con
  `.fillna(0)` o `else 0` para el caso "no vendio nada". Un ACoS de 0 se lee
  como EXCELENTE en cualquier semaforo: el termino que gasto 80 dolares sin
  vender aparecia como el mas eficiente de la tabla, y las reglas de "bajar
  bid si ACoS > X" nunca lo veian.

  El unico valor honesto para "no hay ventas" es None / NaN. No es un cero,
  no es 999, no es un numero grande: es la ausencia del dato. Formatearlo
  para la UI es responsabilidad de quien renderiza, no del calculo.

Alcance:
  Calculo puro. Sin Streamlit, sin I/O, sin formato. Testeable sin levantar
  la app.

Contrato: .claude/skills/ppc-business-invariants.md — INV-7.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _num(v: Any) -> float | None:
    """
    Escalar a float, o None si no hay dato utilizable.

    None, NaN, NaT, string vacio y cualquier cosa no convertible -> None.
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _ratio(numerador: Any, denominador: Any) -> float | None:
    """
    (numerador / denominador) * 100, o None si el denominador no es > 0.

    Motor comun de las tres metricas: las tres son el mismo cociente con
    distinto nombre, y las tres comparten la regla de que un denominador
    en cero no vale cero, vale "sin dato".
    """
    num = _num(numerador)
    den = _num(denominador)
    if num is None or den is None:
        return None
    if den <= 0:
        return None
    return (num / den) * 100.0


def calc_acos(spend: Any, sales: Any) -> float | None:
    """
    ACoS en porcentaje (INV-7).

    Args:
        spend: inversion publicitaria.
        sales: ventas atribuidas.

    Returns:
        (spend / sales) * 100 si sales > 0. None en cualquier otro caso.

    None cuando no hay ventas — nunca 0, nunca 999. Un spend de 0 con ventas
    positivas SI devuelve 0.0: ese es un ACoS de cero real, no una ausencia
    de dato.
    """
    return _ratio(spend, sales)


def calc_cvr(orders: Any, clicks: Any) -> float | None:
    """
    Conversion rate en porcentaje.

    Returns:
        (orders / clicks) * 100 si clicks > 0. None si no.
    """
    return _ratio(orders, clicks)


def calc_ctr(clicks: Any, impressions: Any) -> float | None:
    """
    Click-through rate en porcentaje.

    Returns:
        (clicks / impressions) * 100 si impressions > 0. None si no.
    """
    return _ratio(clicks, impressions)


def acos_series(spend: pd.Series, sales: pd.Series) -> pd.Series:
    """
    Version vectorizada de calc_acos.

    Args:
        spend / sales: Series alineadas por indice.

    Returns:
        Series float64 con el ACoS en porcentaje, y NaN donde sales <= 0 o
        donde alguno de los dos valores no es numerico.

    Deliberadamente SIN fillna: el NaN es el resultado correcto, no un hueco
    a tapar. Quien lo muestre en pantalla decide como formatearlo.
    """
    s = pd.to_numeric(spend, errors="coerce")
    v = pd.to_numeric(sales, errors="coerce")
    # .where(v > 0) manda a NaN tanto los <= 0 como los que ya eran NaN,
    # y con eso la division nunca produce inf ni un cero enganoso.
    den = v.where(v > 0)
    return (s / den * 100.0).astype("float64")

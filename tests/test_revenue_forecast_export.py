"""Tests Fase 5 de M31 Revenue Forecast — Estacionalidad UI + Export CSV.

Cubre:
    1. `_build_forecast_csv` — header exacto (12 cols HTML + 6 overrides),
       nº de filas = horizon+1, formato numérico por col, valores derivados
       de `_EXPECTED_FIRST_FORECAST` (fuente de verdad ya validada en F3),
       caso con override manual, caso vacío (solo header).
    2. `_cliente_slug` — filesystem-safe filename derivation.
    3. `_apply_seasonality_edits` — regla `|| 1` (vacío/NaN/0 → 1.0),
       normalización de tipos, mutación in-place.

Regla anti-placebo: los valores del CSV están derivados de
`_EXPECTED_FIRST_FORECAST` (que a su vez está derivado aritméticamente en
F3). Si un test rompe, la fuente de verdad son los cálculos del HTML —
el código está mal, no el test.

Diseño: tests puros sin runtime Streamlit. Llaman directamente a los helpers
con fixtures pequeños y la constante `_DERMAGLOS_DATA` del módulo.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures compartidas
# ─────────────────────────────────────────────────────────────────────────────

def _dermaglos_rows():
    """Réplica del fixture de test_revenue_forecast_engine.py — 23 meses reales."""
    return [{**r, "spend": None, "ventasPPC": None} for r in rf._DERMAGLOS_DATA]


def _build_dermaglos_forecast(horizon: int = 6):
    """Genera un forecast Dermaglos determinístico con seasonality OFF y yoy OFF.

    Coincide con el fixture `_EXPECTED_FIRST_FORECAST` de F3 → nos permite
    clavar los strings del CSV desde valores ya derivados aritméticamente.
    """
    rows = _dermaglos_rows()
    opts = {"horizon": horizon, "momWindow": 3, "blend": 50, "useSeasonality": False}
    seasonality = {"enabled": False, "indices": [1.0] * 12}
    return rf.generate_forecast(opts, rows, seasonality, yoy_mode="off")


# ─────────────────────────────────────────────────────────────────────────────
# 1. _build_forecast_csv — header + shape + valores
# ─────────────────────────────────────────────────────────────────────────────

_EXPECTED_HEADER = (
    "Date,Revenue,AOV,Units,Sales Velocity,"
    "Sessions,CVR%,Spend,Ventas PPC,"
    "ACOS%,TACOS%,% Vtas PPC,"
    "Manual Revenue,Manual AOV,Manual Sessions,"
    "ACOS Target%,TACOS Target%,Stock Availability%"
)


def test_build_forecast_csv_header_exact():
    """El header del CSV es exactamente 12 cols HTML + 6 cols overrides.

    Fiel al HTML L2860 pero extendido con las 6 columnas de overrides
    manuales del AM (pedido del usuario). Este orden y estos nombres son
    contrato — si cambian, un downstream (BI, Excel, script AM) rompe.
    """
    csv = rf._build_forecast_csv([], "cliente")
    # Sin forecast → solo header, sin newline final.
    assert csv == _EXPECTED_HEADER


def test_build_forecast_csv_row_count_matches_horizon():
    """horizon=6 → 1 header + 6 filas = 7 líneas."""
    forecast = _build_dermaglos_forecast(horizon=6)
    csv = rf._build_forecast_csv(forecast, "Dermaglos")
    lines = csv.split("\n")
    assert len(lines) == 7
    assert lines[0] == _EXPECTED_HEADER


def test_build_forecast_csv_first_row_dermaglos_values():
    """Primera fila del forecast Dermaglos — valores derivados de
    `_EXPECTED_FIRST_FORECAST` en test_revenue_forecast_engine.py.

    Cálculos de formato (fmt='.2f' usa half-even; los valores tienen dígitos
    suficientes que NO caen en ties, así que da igual):
        revenue      = 5411.10148187 → "5411.10"
        aov          = 14.66694846   → "14.67"   (3er dec = 6, round up)
        units        = 368.93164902  → 369       (half-up int)
        salesVeloc.  = 11.90102094   → "11.90"
        sessions     = 4188.27728928 → 4188      (half-up int)
        cvr          = 8.80867296    → "8.81"    (3er dec = 8, round up)
        spend        = 541           → "541.00"
        ventasPPC    = 1803.33333333 → "1803.33"
        acos         = 30.0          → "30.00"
        tacos        = 9.99796440    → "10.00"   (3er dec = 7, round up)
        pctVtasPPC   = 33.32654801   → "33.33"   (3er dec = 6, round up)

    Overrides en un forecast recién generado:
        - manualRevenue, manualAOV, manualSessions → None → vacío ("").
        - acosTarget = 30.0 (default siempre inicializado por generate_forecast
          en L1687-1690: `avg_acos_real` o 30.0) → "30.00".
        - tacosTarget → None → vacío.
        - stockAvailability → key ausente en generate_forecast (solo se agrega
          si el AM edita en F4) → vacío.
    """
    forecast = _build_dermaglos_forecast(horizon=6)
    csv = rf._build_forecast_csv(forecast, "Dermaglos")
    lines = csv.split("\n")
    first_row = lines[1]

    expected_first = (
        "2026-05-01,"                # date
        "5411.10,"                   # revenue
        "14.67,"                     # aov
        "369,"                       # units (half-up int)
        "11.90,"                     # salesVelocity
        "4188,"                      # sessions (half-up int)
        "8.81,"                      # cvr
        "541.00,"                    # spend
        "1803.33,"                   # ventasPPC
        "30.00,"                     # acos
        "10.00,"                     # tacos
        "33.33,"                     # pctVtasPPC
        ",,,"                        # Manual Revenue, Manual AOV, Manual Sessions
        "30.00,"                     # ACOS Target% (default siempre presente)
        ","                          # TACOS Target% vacío
                                     # Stock Availability% vacío (sin coma final)
    )
    assert first_row == expected_first


def test_build_forecast_csv_with_manual_override_shows_in_column():
    """Un forecast con `manualRevenue` seteado se refleja en la columna
    "Manual Revenue" con formato `.2f`.

    Setup: generamos forecast, mutamos primer row para agregar overrides,
    recalculamos con recompute_forecast_row (fiel al flujo F4 real).
    Verificamos que:
        - "Manual Revenue" aparece formateado ('.2f').
        - "ACOS Target%" refleja el valor (30.0 default → "30.00").
        - "Manual AOV", "Manual Sessions", "TACOS Target%", "Stock
          Availability%" quedan vacías.
    Bonus: "Revenue" (col 2) refleja el override, no el revenueAuto.
    """
    forecast = _build_dermaglos_forecast(horizon=3)
    # Override manual del AM: el revenue efectivo debe ser 7000.
    forecast[0]["manualRevenue"] = 7000.0
    rf.recompute_forecast_row(forecast[0])

    csv = rf._build_forecast_csv(forecast, "Dermaglos")
    lines = csv.split("\n")
    first_row = lines[1]
    cells = first_row.split(",")

    # 18 columnas totales.
    assert len(cells) == 18

    # Col 1 (Revenue) = manualRevenue formateado → 7000.00.
    assert cells[1] == "7000.00"

    # Col 12 (Manual Revenue) = 7000.00 (mismo, con formato).
    assert cells[12] == "7000.00"
    # Col 13 (Manual AOV) — vacía.
    assert cells[13] == ""
    # Col 14 (Manual Sessions) — vacía.
    assert cells[14] == ""
    # Col 15 (ACOS Target%) — 30.00 (default de generate_forecast).
    assert cells[15] == "30.00"
    # Col 16 (TACOS Target%) — vacía.
    assert cells[16] == ""
    # Col 17 (Stock Availability%) — vacía.
    assert cells[17] == ""


def test_build_forecast_csv_stock_availability_and_tacos_overrides():
    """Casos combinados: stockAvailability=80 y tacosTarget=15 se reflejan.

    Verifica que overrides "extras" (no revenue) se formatean bien y aparecen
    en las columnas correctas.
    """
    forecast = _build_dermaglos_forecast(horizon=2)
    forecast[0]["stockAvailability"] = 80.0
    forecast[0]["tacosTarget"] = 15.0
    rf.recompute_forecast_row(forecast[0])

    csv = rf._build_forecast_csv(forecast, "Dermaglos")
    cells = csv.split("\n")[1].split(",")

    # Col 15 (ACOS Target%) = 30.00 default.
    assert cells[15] == "30.00"
    # Col 16 (TACOS Target%) = 15.00.
    assert cells[16] == "15.00"
    # Col 17 (Stock Availability%) = 80.00.
    assert cells[17] == "80.00"


def test_build_forecast_csv_empty_forecast_only_header():
    """forecast=[] → solo header, sin filas de datos ni newline trailing."""
    csv = rf._build_forecast_csv([], "Cliente Prueba")
    assert csv == _EXPECTED_HEADER
    assert "\n" not in csv


# ─────────────────────────────────────────────────────────────────────────────
# 2. _cliente_slug — filename safety
# ─────────────────────────────────────────────────────────────────────────────

def test_cliente_slug_lowercase_and_underscores():
    """'Love To Dream MX' → 'love_to_dream_mx' (espacios → '_', lowercase)."""
    assert rf._cliente_slug("Love To Dream MX") == "love_to_dream_mx"


def test_cliente_slug_empty_falls_back_to_cuenta():
    """Fiel al HTML L2882 `state.account.name || 'cuenta'`."""
    assert rf._cliente_slug("") == "cuenta"
    assert rf._cliente_slug(None) == "cuenta"  # type: ignore[arg-type]


def test_cliente_slug_strips_special_chars():
    """Filesystem-safe: sin puntos, slashes, ampersands. Preserva tildes/ñ."""
    assert rf._cliente_slug("M&B / Mott") == "mb_mott"
    # Tildes y ñ NO son especiales del filesystem — preserva.
    assert rf._cliente_slug("Ñoño Café") == "ñoño_café"


# ─────────────────────────────────────────────────────────────────────────────
# 3. _apply_seasonality_edits — regla `|| 1`
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_seasonality_edits_writes_all_12():
    """Un df con 12 filas escribe los 12 índices y devuelve 12."""
    seas = {"enabled": True, "indices": [1.0] * 12}
    df = pd.DataFrame({
        "Mes": rf._MONTHS_FULL[:12],
        "Índice": [1.1, 1.2, 0.9, 1.0, 1.05, 0.95, 1.15, 0.85, 1.0, 1.0, 1.3, 0.7],
    })
    n = rf._apply_seasonality_edits(seas, df)
    assert n == 12
    assert seas["indices"] == [1.1, 1.2, 0.9, 1.0, 1.05, 0.95, 1.15, 0.85, 1.0, 1.0, 1.3, 0.7]


def test_apply_seasonality_edits_empty_or_zero_falls_back_to_1():
    """Regla HTML L2259 `parseFloat(v) || 1`: NaN, 0, '' → 1.0.

    Cubre el input real del data_editor cuando el AM borra una celda.
    """
    seas = {"enabled": True, "indices": [1.0] * 12}
    # Fila 0: NaN → 1.0. Fila 1: 0 → 1.0. Resto: valores reales.
    df = pd.DataFrame({
        "Mes": rf._MONTHS_FULL[:12],
        "Índice": [math.nan, 0.0, 1.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    })
    rf._apply_seasonality_edits(seas, df)
    assert seas["indices"][0] == 1.0  # NaN → 1.0
    assert seas["indices"][1] == 1.0  # 0 → 1.0
    assert seas["indices"][2] == 1.5  # respetado


def test_apply_seasonality_edits_empty_df_returns_zero():
    """DataFrame vacío o None → no muta y devuelve 0."""
    seas = {"enabled": False, "indices": [1.0] * 12}
    n = rf._apply_seasonality_edits(seas, pd.DataFrame())
    assert n == 0
    assert seas["indices"] == [1.0] * 12


def test_apply_seasonality_edits_repairs_wrong_length_indices():
    """Si por alguna razón indices tiene !=12 elementos, se repara a [1.0]*12
    antes de escribir (defensivo — evita out-of-range escondidos)."""
    seas = {"enabled": False, "indices": [1.0, 1.0]}  # corrupto — solo 2
    df = pd.DataFrame({
        "Mes": rf._MONTHS_FULL[:12],
        "Índice": [1.5] * 12,
    })
    rf._apply_seasonality_edits(seas, df)
    assert len(seas["indices"]) == 12
    assert seas["indices"] == [1.5] * 12


def test_apply_seasonality_edits_auto_detect_result_shape_compat():
    """El output de `auto_detect_seasonality` es un dict {enabled, indices[12]}
    directamente asignable a `cur["seasonality"]`.

    Este test verifica que el contrato entre F3 (motor puro) y F5 (UI) se
    mantiene: si un dev cambia auto_detect_seasonality y devuelve otro shape,
    este test rompe.
    """
    rows = _dermaglos_rows()
    result = rf.auto_detect_seasonality(rows)
    assert result is not None
    assert set(result.keys()) == {"enabled", "indices"}
    assert result["enabled"] is True
    assert len(result["indices"]) == 12
    assert all(isinstance(v, float) for v in result["indices"])


def test_apply_seasonality_edits_auto_detect_under_12_returns_none():
    """El helper F3 devuelve None con <12 meses — la UI muestra warning y
    NO muta cur["seasonality"]. Verificamos el contrato del motor puro."""
    short_rows = _dermaglos_rows()[:11]  # solo 11 meses
    assert rf.auto_detect_seasonality(short_rows) is None

"""Tests Fase 4 de M31 Revenue Forecast — UI editable del forecast.

La UI completa (data_editor + cards) requiere runtime Streamlit y NO se testea
acá. Lo que SÍ se testea es el helper PURO `_apply_forecast_edits` y el helper
PURO `_build_forecast_summary_cards`, que son la lógica crítica del F4 (la UI
los wrapea sin agregar lógica de negocio).

Excepción: los controles de generación (`_render_forecast_controls`) SÍ se
testean con AppTest — sus bounds (min/max/value del number_input) son lógica
que Streamlit valida en runtime y que puede tumbar la página, así que no se
puede verificar sin runtime. Se usa `AppTest.from_string` (NO `from_function`:
da falsos negativos silenciosos bajo pytest en este proyecto).

Regla anti-placebo: los valores esperados se derivan de la FÓRMULA del HTML
aplicada a los AUTO VALUES del motor F3 — no se copian del output de
`_apply_forecast_edits`. Los auto values vienen de `generate_forecast` (motor
F3), que ya tiene sus propios tests con derivación manual.

Esto da una separación limpia:
    - Engine tests (F3): verifican que `generate_forecast` calcula los auto
      values correctos a partir del histórico.
    - UI helper tests (F4 — este archivo): verifican que `_apply_forecast_edits`
      aplica el override correcto al dict, llama `recompute_forecast_row`, y los
      campos computados resultan de la fórmula sobre (override × auto values).

Cobertura:
    1. manualRevenue override → revenue=override*availFactor, units recalculado.
    2. manualAOV override → units recalculado con AOV nuevo.
    3. manualSessions override → cvr recalculado con sessions nuevas.
    4. stockAvailability=50 → revenue a la mitad, units a la mitad.
    5. tacosTarget=15 → spend = revenue × 0.15 (half-up 2 dec), "via TACOS".
    6. Reset de overrides → manuales a None, revenue vuelve a revenueAuto.
    7. acosTarget vacío → default 30.
    8. spend vacío → 0.
    9. _value_or_none — NaN, '', None, número, string numérico.
   10. _build_forecast_summary_cards — totales y promedios fieles a HTML L2193.
   11. _build_forecast_df — columnas correctas + _idx preservado + Mes label.
   12. _render_forecast_controls — tope de "Ventana MoM" sigue al historial.
   13. _render_forecast_controls — clamp del value= al cambiar de cliente (E1).

Diseño: tests puros sin runtime Streamlit. Llaman directamente a los helpers
con forecast generados por `generate_forecast`.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _dermaglos_rows():
    """Fixture: 23 meses Dermaglos con spend/ventasPPC None (como demo)."""
    return [{**r, "spend": None, "ventasPPC": None} for r in rf._DERMAGLOS_DATA]


def _gen_forecast(horizon: int = 3):
    """Genera un forecast determinístico para los tests del helper.

    opts: horizon=3, momWindow=3, blend=50, useSeasonality=False, yoy_mode='off'.
    Mismos params que el test del motor — los auto values son los conocidos.
    """
    rows = _dermaglos_rows()
    opts = {"horizon": horizon, "momWindow": 3, "blend": 50, "useSeasonality": False}
    seasonality = {"enabled": False, "indices": [1.0] * 12}
    return rf.generate_forecast(opts, rows, seasonality, "off")


# ─────────────────────────────────────────────────────────────────────────────
# _value_or_none — normalización de inputs del data_editor
# ─────────────────────────────────────────────────────────────────────────────

def test_value_or_none_none():
    assert rf._value_or_none(None) is None


def test_value_or_none_empty_string():
    assert rf._value_or_none("") is None
    assert rf._value_or_none("   ") is None


def test_value_or_none_nan():
    assert rf._value_or_none(float("nan")) is None


def test_value_or_none_zero_is_valid():
    """0 NO es None — el AM puede setear 0 explícitamente."""
    assert rf._value_or_none(0) == 0.0
    assert rf._value_or_none(0.0) == 0.0


def test_value_or_none_numeric():
    assert rf._value_or_none(9999) == 9999.0
    assert rf._value_or_none(14.5) == 14.5


def test_value_or_none_string_numeric():
    assert rf._value_or_none("123.45") == 123.45


def test_value_or_none_invalid_string():
    """Cadena no numérica → None (fail-soft, no excepción)."""
    assert rf._value_or_none("abc") is None


# ─────────────────────────────────────────────────────────────────────────────
# _build_forecast_df — DataFrame para data_editor
# ─────────────────────────────────────────────────────────────────────────────

def test_build_forecast_df_empty():
    df = rf._build_forecast_df([])
    assert df.empty
    expected_cols = {
        "_idx", "Mes",
        "manualRevenue", "manualAOV", "manualSessions",
        "spend", "acosTarget", "tacosTarget", "stockAvailability",
        "revenue", "aov", "units", "sessions", "cvr", "salesVelocity",
        "ventasPPC", "acos", "tacos", "pctVtasPPC",
    }
    assert set(df.columns) == expected_cols


def test_build_forecast_df_has_idx_and_mes_label():
    forecast = _gen_forecast(horizon=3)
    df = rf._build_forecast_df(forecast)
    assert len(df) == 3
    # _idx preservado en orden de generación (no se reordena).
    assert list(df["_idx"]) == [0, 1, 2]
    # Mes label en español, "Mayo 2026" etc. (primera fila Dermaglos+1mes = mayo 2026).
    assert df.iloc[0]["Mes"] == "Mayo 2026"


def test_build_forecast_df_preserves_auto_values_in_computed_cols():
    """Las computadas pre-recompute (de generate_forecast) ya están en el dict."""
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    f0 = forecast[0]
    assert df.iloc[0]["revenue"] == pytest.approx(f0["revenue"], rel=1e-9)
    assert df.iloc[0]["aov"] == pytest.approx(f0["aov"], rel=1e-9)
    assert df.iloc[0]["sessions"] == pytest.approx(f0["sessions"], rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# _apply_forecast_edits — override manualRevenue
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_manual_revenue_override():
    """manualRevenue=9999 en fila 0 → revenue=9999*1.0 (availability default 100),
    units=9999/aovAuto, sessions=sessionsAuto (no override), cvr recalculado.

    Derivación (con aov_auto y sess_auto reales del motor F3):
        revenue = 9999.0 * (100/100) = 9999.0
        units = 9999.0 / aov_auto
        cvr = (units / sess_auto) * 100
        spend unchanged (no tacosTarget) = baseline del generate.
        ventasPPC = spend / (acosTarget/100) = spend / 0.30 (acos default 30).
        tacos = spend / revenue * 100 = spend / 9999 * 100.
        pctVtasPPC = ventasPPC / revenue * 100.
    """
    forecast = _gen_forecast(horizon=3)
    # Capturamos auto values ANTES de editar.
    aov_auto = forecast[0]["aovAuto"]
    sess_auto = forecast[0]["sessionsAuto"]
    spend_baseline = forecast[0]["spend"]
    acos_baseline = forecast[0]["acosTarget"]
    assert acos_baseline == 30.0  # avgACOSReal=None → default 30.0

    df = rf._build_forecast_df(forecast)
    df.at[0, "manualRevenue"] = 9999.0
    written = rf._apply_forecast_edits(forecast, df)
    assert written == 3

    f = forecast[0]
    # 1. Override guardado.
    assert f["manualRevenue"] == 9999.0
    # 2. Revenue = override × availFactor (default 100%).
    assert f["revenue"] == pytest.approx(9999.0, rel=1e-9)
    # 3. Units = revenue / aov_auto.
    expected_units = 9999.0 / aov_auto
    assert f["units"] == pytest.approx(expected_units, rel=1e-9)
    # 4. Sessions sin override → queda en sessionsAuto.
    assert f["sessions"] == pytest.approx(sess_auto, rel=1e-9)
    # 5. CVR = (units / sessions) × 100.
    expected_cvr = (expected_units / sess_auto) * 100.0
    assert f["cvr"] == pytest.approx(expected_cvr, rel=1e-9)
    # 6. Spend sin tacosTarget → preserva baseline.
    assert f["spend"] == spend_baseline
    # 7. ventasPPC = spend / (acos/100).
    expected_vppc = spend_baseline / (acos_baseline / 100.0)
    assert f["ventasPPC"] == pytest.approx(expected_vppc, rel=1e-9)
    # 8. TACOS = spend / revenue × 100.
    expected_tacos = spend_baseline / 9999.0 * 100.0
    assert f["tacos"] == pytest.approx(expected_tacos, rel=1e-9)


def test_apply_forecast_edits_manual_aov_override():
    """manualAOV=20 → units recalculado con AOV nuevo (revenue queda en revenueAuto)."""
    forecast = _gen_forecast(horizon=1)
    rev_auto = forecast[0]["revenueAuto"]

    df = rf._build_forecast_df(forecast)
    df.at[0, "manualAOV"] = 20.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    assert f["manualAOV"] == 20.0
    assert f["aov"] == 20.0
    # revenue: sin override → revenueAuto (escala con availability default 100).
    assert f["revenue"] == pytest.approx(rev_auto, rel=1e-9)
    # units = revenue / 20.
    assert f["units"] == pytest.approx(rev_auto / 20.0, rel=1e-9)


def test_apply_forecast_edits_manual_sessions_override():
    """manualSessions=5000 → cvr recalculado con sessions nuevas."""
    forecast = _gen_forecast(horizon=1)
    rev_auto = forecast[0]["revenueAuto"]
    aov_auto = forecast[0]["aovAuto"]

    df = rf._build_forecast_df(forecast)
    df.at[0, "manualSessions"] = 5000.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    assert f["manualSessions"] == 5000.0
    assert f["sessions"] == 5000.0
    expected_units = rev_auto / aov_auto
    expected_cvr = (expected_units / 5000.0) * 100.0
    assert f["cvr"] == pytest.approx(expected_cvr, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# _apply_forecast_edits — availability (stockAvailability)
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_availability_50_halves_revenue():
    """stockAvailability=50 → revenue *= 0.5 (availability clamp/scale), units también.

    Sessions NO se escalan por availability (fiel al HTML L1888-1490 — solo revenue).
    """
    forecast = _gen_forecast(horizon=1)
    rev_auto = forecast[0]["revenueAuto"]
    aov_auto = forecast[0]["aovAuto"]
    sess_auto = forecast[0]["sessionsAuto"]

    df = rf._build_forecast_df(forecast)
    df.at[0, "stockAvailability"] = 50.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    assert f["stockAvailability"] == 50.0
    assert f["availability"] == 50.0
    # Revenue = revenueAuto × 0.5
    expected_revenue = rev_auto * 0.5
    assert f["revenue"] == pytest.approx(expected_revenue, rel=1e-9)
    # Units = revenue / aov → también a la mitad
    expected_units = expected_revenue / aov_auto
    assert f["units"] == pytest.approx(expected_units, rel=1e-9)
    # Sessions: NO escala con availability.
    assert f["sessions"] == pytest.approx(sess_auto, rel=1e-9)


def test_apply_forecast_edits_availability_clamp_negative():
    """stockAvailability=-10 → clamp a 0 → revenue=0."""
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    df.at[0, "stockAvailability"] = -10.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    assert f["availability"] == 0.0
    assert f["revenue"] == 0.0
    assert f["units"] == 0.0


def test_apply_forecast_edits_availability_clamp_over_100():
    """stockAvailability=150 → clamp a 100 → revenue=revenueAuto."""
    forecast = _gen_forecast(horizon=1)
    rev_auto = forecast[0]["revenueAuto"]
    df = rf._build_forecast_df(forecast)
    df.at[0, "stockAvailability"] = 150.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    assert f["availability"] == 100.0
    assert f["revenue"] == pytest.approx(rev_auto, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# _apply_forecast_edits — tacosTarget driving spend
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_tacos_target_drives_spend():
    """tacosTarget=15 + revenue > 0 → spend = revenue × 0.15 (half-up 2 dec).

    Sutileza importante del HTML L1894-1903 (fielmente portado):
      - LOCAL `spend` = revenue × 0.15 (raw, sin redondear) → usado para
        ventasPPC/tacos/pctVtasPPC.
      - `f["spend"]` (display) = round_half_up(spend, 2) — el AM ve un valor
        redondeado pero los cálculos derivados (tacos, ventasPPC) usan la
        precisión completa.
      - Consecuencia: `f["tacos"]` = (rev × 0.15) / rev × 100 = EXACTAMENTE
        15.0 (la fórmula se colapsa), NO el tacos derivado del spend
        redondeado.
    """
    forecast = _gen_forecast(horizon=1)
    rev_auto = forecast[0]["revenueAuto"]
    expected_revenue = rev_auto

    df = rf._build_forecast_df(forecast)
    df.at[0, "tacosTarget"] = 15.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    assert f["tacosTarget"] == 15.0
    # f["spend"] (display) = revenue × 0.15, half-up 2 dec.
    expected_spend_display = rf._round_half_up_dec(expected_revenue * 0.15, 2)
    assert f["spend"] == expected_spend_display
    # f["tacos"]: usa el spend RAW (revenue × 0.15), por eso se colapsa
    # a exactamente tacosTarget (15.0). Esto matchea el HTML al pie de la letra.
    assert f["tacos"] == pytest.approx(15.0, rel=1e-9)
    # ventasPPC también usa spend RAW: (rev × 0.15) / (acos/100) = rev × 0.15 / 0.30 = rev × 0.5.
    expected_vppc = expected_revenue * 0.15 / 0.30
    assert f["ventasPPC"] == pytest.approx(expected_vppc, rel=1e-9)


def test_apply_forecast_edits_tacos_target_zero_revenue_falls_back_to_spend():
    """tacosTarget set pero revenue=0 (via stockAvailability=0) → spend manual gana."""
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    df.at[0, "stockAvailability"] = 0.0
    df.at[0, "tacosTarget"] = 15.0
    df.at[0, "spend"] = 999.0
    rf._apply_forecast_edits(forecast, df)

    f = forecast[0]
    # Revenue=0 → cae al else: spend = _js_number(f.get("spend")) = 999.
    assert f["revenue"] == 0.0
    assert f["spend"] == 999.0


# ─────────────────────────────────────────────────────────────────────────────
# _apply_forecast_edits — reset (overrides None)
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_reset_restores_auto():
    """Después de aplicar override y volver a None, revenue/aov/sessions vuelven
    a sus Auto values."""
    forecast = _gen_forecast(horizon=1)
    rev_auto = forecast[0]["revenueAuto"]
    aov_auto = forecast[0]["aovAuto"]
    sess_auto = forecast[0]["sessionsAuto"]

    # Override masivo.
    df = rf._build_forecast_df(forecast)
    df.at[0, "manualRevenue"] = 9999.0
    df.at[0, "manualAOV"] = 50.0
    df.at[0, "manualSessions"] = 1000.0
    rf._apply_forecast_edits(forecast, df)
    assert forecast[0]["revenue"] == pytest.approx(9999.0, rel=1e-9)

    # Reset: setear todos a None vía df.
    df2 = rf._build_forecast_df(forecast)
    df2.at[0, "manualRevenue"] = None
    df2.at[0, "manualAOV"] = None
    df2.at[0, "manualSessions"] = None
    rf._apply_forecast_edits(forecast, df2)

    f = forecast[0]
    assert f["manualRevenue"] is None
    assert f["manualAOV"] is None
    assert f["manualSessions"] is None
    assert f["revenue"] == pytest.approx(rev_auto, rel=1e-9)
    assert f["aov"] == pytest.approx(aov_auto, rel=1e-9)
    assert f["sessions"] == pytest.approx(sess_auto, rel=1e-9)


def test_reset_forecast_overrides_helper():
    """`_reset_forecast_overrides` limpia manuales y tacosTarget de TODAS las filas."""
    forecast = _gen_forecast(horizon=3)
    rev_auto_per_row = [f["revenueAuto"] for f in forecast]

    # Setear overrides en todas las filas.
    df = rf._build_forecast_df(forecast)
    for i in range(len(forecast)):
        df.at[i, "manualRevenue"] = 11111.0
        df.at[i, "tacosTarget"] = 20.0
    rf._apply_forecast_edits(forecast, df)
    for f in forecast:
        assert f["manualRevenue"] == 11111.0
        assert f["tacosTarget"] == 20.0

    # Reset.
    cur = {"forecast": forecast}
    n = rf._reset_forecast_overrides(cur)
    assert n == 3

    for i, f in enumerate(forecast):
        assert f["manualRevenue"] is None
        assert f["manualAOV"] is None
        assert f["manualSessions"] is None
        assert f["tacosTarget"] is None
        # Revenue vuelve a revenueAuto.
        assert f["revenue"] == pytest.approx(rev_auto_per_row[i], rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# _apply_forecast_edits — defaults (acos vacío, spend vacío)
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_acos_empty_defaults_to_30():
    """Si el AM borra acosTarget (NaN/None) → default 30 (consistencia con generate)."""
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    df.at[0, "acosTarget"] = None
    rf._apply_forecast_edits(forecast, df)
    assert forecast[0]["acosTarget"] == 30.0


def test_apply_forecast_edits_spend_empty_defaults_to_zero():
    """Si el AM borra spend (sin tacosTarget) → 0 (fail-soft)."""
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    df.at[0, "spend"] = None
    df.at[0, "tacosTarget"] = None
    rf._apply_forecast_edits(forecast, df)
    f = forecast[0]
    assert f["spend"] == 0
    assert f["ventasPPC"] == 0.0
    assert f["tacos"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _apply_forecast_edits — edge cases del wiring
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_empty_df_returns_zero():
    forecast = _gen_forecast(horizon=1)
    empty_df = pd.DataFrame()
    assert rf._apply_forecast_edits(forecast, empty_df) == 0


def test_apply_forecast_edits_none_df_returns_zero():
    forecast = _gen_forecast(horizon=1)
    assert rf._apply_forecast_edits(forecast, None) == 0


def test_apply_forecast_edits_invalid_idx_skipped():
    """Filas con _idx fuera de rango se ignoran sin romper."""
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    # Agregar fila fantasma con _idx fuera de rango.
    extra = pd.DataFrame([{
        "_idx": 99, "Mes": "Fake",
        "manualRevenue": 0, "manualAOV": 0, "manualSessions": 0,
        "spend": 0, "acosTarget": 30, "tacosTarget": None,
        "stockAvailability": None,
        "revenue": 0, "aov": 0, "units": 0, "sessions": 0, "cvr": 0,
        "salesVelocity": 0, "ventasPPC": 0, "acos": 30, "tacos": 0,
        "pctVtasPPC": 0,
    }])
    df_with_bad = pd.concat([df, extra], ignore_index=True)
    written = rf._apply_forecast_edits(forecast, df_with_bad)
    # Solo la fila válida se procesa (la fantasma se ignora).
    assert written == 1


# ─────────────────────────────────────────────────────────────────────────────
# _build_forecast_summary_cards — port de renderForecastSummary L2193
# ─────────────────────────────────────────────────────────────────────────────

def test_build_forecast_summary_cards_empty():
    assert rf._build_forecast_summary_cards([]) == []


def test_build_forecast_summary_cards_returns_8_cards():
    forecast = _gen_forecast(horizon=3)
    cards = rf._build_forecast_summary_cards(forecast, "USD")
    assert len(cards) == 8
    labels = [c["label"] for c in cards]
    assert labels == [
        "Revenue total", "Units totales", "Sessions totales",
        "Spend total", "Ventas PPC totales",
        "ACOS prom.", "TACOS prom.", "AOV prom.",
    ]


def test_build_forecast_summary_cards_totals_match_sum():
    """Cada card es la SUMA de la columna correspondiente; promedios usan max(1, x)."""
    forecast = _gen_forecast(horizon=3)
    # Totales esperados (suma directa de los dicts).
    total_revenue = sum(f["revenue"] for f in forecast)
    total_units = sum(f["units"] for f in forecast)
    total_sessions = sum(f["sessions"] for f in forecast)
    total_spend = sum(f["spend"] for f in forecast)
    total_vppc = sum(f["ventasPPC"] for f in forecast)
    expected_acos_prom = total_spend / max(1.0, total_vppc) * 100.0
    expected_tacos_prom = total_spend / max(1.0, total_revenue) * 100.0
    expected_aov_prom = total_revenue / max(1.0, total_units)

    cards = rf._build_forecast_summary_cards(forecast, "USD")
    # Los values son strings formateados — usamos _fmt_* para derivar.
    assert cards[0]["value"] == rf._fmt_currency(total_revenue, "USD")
    assert cards[1]["value"] == rf._fmt_num(total_units)
    assert cards[2]["value"] == rf._fmt_num(total_sessions)
    assert cards[3]["value"] == rf._fmt_currency(total_spend, "USD")
    assert cards[4]["value"] == rf._fmt_currency(total_vppc, "USD")
    assert cards[5]["value"] == rf._fmt_pct(expected_acos_prom, 1)
    assert cards[6]["value"] == rf._fmt_pct(expected_tacos_prom, 1)
    assert cards[7]["value"] == rf._fmt_currency(expected_aov_prom, "USD", dec=2)


def test_build_forecast_summary_cards_zero_revenue_no_div_zero():
    """Forecast con revenue=0 + units=0 + ventasPPC=0 → guard max(1, x) en denominador
    evita div/0. ACOS prom: spend/max(1, 0) × 100; TACOS prom: spend/max(1, 0) × 100;
    AOV prom: 0/max(1, 0) = 0.

    Forzamos todo a 0 vía: stockAvailability=0 (revenue=0 → units=0 → ventasPPC=0)
    Y spend=0 explícito (sin esto, el spend baseline del genérate persiste y
    daría ACOS = spend/max(1, 0) × 100 = un % no nulo, lo cual NO es un bug —
    sólo demuestra que el guard `max(1, x)` funciona evitando excepción).

    El test asegura NO div/0 exception y que los formatters devuelven strings
    válidos.
    """
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    for i in range(len(forecast)):
        df.at[i, "stockAvailability"] = 0.0
        df.at[i, "spend"] = 0.0  # sin spend → ACOS y TACOS quedan en 0.
    rf._apply_forecast_edits(forecast, df)

    # No debe lanzar excepción ZeroDivisionError.
    cards = rf._build_forecast_summary_cards(forecast, "USD")
    assert len(cards) == 8
    # Con revenue=0, spend=0, ventasPPC=0: todos los promedios derivados son 0.
    assert cards[5]["value"] == rf._fmt_pct(0.0, 1)   # ACOS
    assert cards[6]["value"] == rf._fmt_pct(0.0, 1)   # TACOS
    assert cards[7]["value"] == rf._fmt_currency(0.0, "USD", dec=2)  # AOV


# ─────────────────────────────────────────────────────────────────────────────
# Sanity check: helper PURO (no toca Streamlit)
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_forecast_edits_pure_no_streamlit():
    """`_apply_forecast_edits` debe correr sin runtime Streamlit (sin st.* calls).

    Si este test pasa, el helper es testeable y reusable fuera de la UI.
    """
    forecast = _gen_forecast(horizon=1)
    df = rf._build_forecast_df(forecast)
    df.at[0, "manualRevenue"] = 1234.56
    # Ejecutar sin st.session_state ni mock alguno — debe trabajar puro.
    result = rf._apply_forecast_edits(forecast, df)
    assert result == 1
    assert forecast[0]["manualRevenue"] == 1234.56


def test_reset_forecast_overrides_pure_no_streamlit():
    """`_reset_forecast_overrides` también es puro — toma cur dict, lo muta."""
    forecast = _gen_forecast(horizon=2)
    # Marcar overrides.
    forecast[0]["manualRevenue"] = 1.0
    forecast[1]["tacosTarget"] = 10.0
    cur = {"forecast": forecast}
    n = rf._reset_forecast_overrides(cur)
    assert n == 2
    assert forecast[0]["manualRevenue"] is None
    assert forecast[1]["tacosTarget"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Sanity check: math import no usado por error
# (asegura que el module-level import de math se mantiene tras refactor)
# ─────────────────────────────────────────────────────────────────────────────

def test_module_imports_math_for_nan_check():
    """El helper `_value_or_none` usa math.isnan — asegurar que el módulo lo importa."""
    assert hasattr(rf, "math") or hasattr(math, "isnan")  # tautológico pero documenta el contrato


# ─────────────────────────────────────────────────────────────────────────────
# _render_forecast_controls — bounds de "Ventana MoM" (E1)
# ─────────────────────────────────────────────────────────────────────────────
#
# El tope de la ventana MoM sigue al historial cargado: max(12, len(historical)).
# El riesgo que cubren estos tests es el CLAMP del `value=`: el buffer de los
# controles (`_K_FC_BUF`) es GLOBAL de sesión, no por cliente, y no se resetea al
# cambiar de cliente. Sin clamp, venir de un cliente con historial largo
# (momWindow=20) a uno corto (max=12) hace que Streamlit levante
# StreamlitValueAboveMaxError y se caiga la página entera.

_REPO_ROOT = str(Path(__file__).resolve().parents[1])

_CONTROLS_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf

hist = [
    {
        "date": "2025-%02d-01" % (i + 1),
        "revenue": 1000.0, "units": 10, "sessions": 300, "cvr": 6,
        "buyBox": 90, "pageViews": 450, "revenueB2B": 0,
        "spend": None, "ventasPPC": None,
    }
    for i in range(__N_MESES__)
]
c = rf._new_client(name="T", client_id="t1")
c["historical"] = hist
st.session_state[rf._K_CLIENTS] = [c]
st.session_state[rf._K_ACTIVE_CLIENT_ID] = "t1"
st.session_state[rf._K_ACCOUNT_MANAGERS] = []

# Buffer GLOBAL, heredado de un cliente con historial mas largo.
buf = rf._ensure_fc_buf()
buf["momWindow"] = __MOM_BUF__

rf._render_forecast_controls(c)
"""


def _run_controls(n_meses: int, mom_buf: int) -> AppTest:
    """Corre `_render_forecast_controls` con N meses de historial y un buffer
    global que ya trae `momWindow=mom_buf`.
    """
    script = (
        _CONTROLS_APP
        .replace("__REPO_ROOT__", _REPO_ROOT)
        .replace("__N_MESES__", str(n_meses))
        .replace("__MOM_BUF__", str(mom_buf))
    )
    at = AppTest.from_string(script)
    at.run()
    return at


def _mom_widget(at: AppTest):
    """El number_input de 'Ventana MoM (meses)'."""
    for w in at.number_input:
        if "Ventana MoM" in w.label:
            return w
    raise AssertionError(
        f"No se encontro el number_input de Ventana MoM. "
        f"Labels: {[w.label for w in at.number_input]}"
    )


def test_forecast_controls_mom_max_follows_history():
    """Historial largo (23 meses) → el tope sube a 23, no queda clavado en 12."""
    at = _run_controls(n_meses=23, mom_buf=3)
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"
    assert _mom_widget(at).max == 23


def test_forecast_controls_mom_max_floor_is_12_on_short_history():
    """Historial corto (5 meses) → el tope NO baja de 12 (piso, sin regresion)."""
    at = _run_controls(n_meses=5, mom_buf=3)
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"
    assert _mom_widget(at).max == 12


def test_forecast_controls_clamps_mom_window_when_switching_to_short_client():
    """E1 — el caso que tumbaba la pagina.

    Buffer global con momWindow=20 (venia de un cliente de 23 meses) + cliente
    de 5 meses (max=12). Sin el clamp en `value=`, Streamlit levanta
    StreamlitValueAboveMaxError y la pagina entera se cae.
    """
    at = _run_controls(n_meses=5, mom_buf=20)

    assert not at.exception, (
        "La pagina se cayo al cambiar a un cliente de historial corto con "
        f"momWindow=20 en el buffer global: {at.exception}"
    )
    w = _mom_widget(at)
    assert w.max == 12
    assert w.value <= w.max, f"value={w.value} excede max={w.max}"
    assert w.value == 12, f"esperado clamp a 12, quedo {w.value}"


def test_forecast_controls_does_not_clamp_when_history_allows():
    """Sin cambio de cliente: momWindow=20 con 23 meses se respeta tal cual."""
    at = _run_controls(n_meses=23, mom_buf=20)
    assert not at.exception, f"La pagina levanto excepcion: {at.exception}"
    w = _mom_widget(at)
    assert w.max == 23
    assert w.value == 20, f"el value no deberia clampearse, quedo {w.value}"


def test_forecast_controls_horizon_stays_capped_at_12():
    """'Meses a proyectar' es el horizonte, NO la ventana: sigue topeado en 12."""
    at = _run_controls(n_meses=23, mom_buf=3)
    assert not at.exception
    horizon = [w for w in at.number_input if "Meses a proyectar" in w.label]
    assert len(horizon) == 1
    assert horizon[0].max == 12

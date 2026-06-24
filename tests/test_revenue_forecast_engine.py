"""Tests Fase 3 de M31 Revenue Forecast — motor de cálculo + estacionalidad.

Cubre las funciones puras del motor (port verbatim del JS del HTML, sección
FORECAST ENGINE). Los valores esperados están DERIVADOS ARITMÉTICAMENTE de
los inputs y la fórmula del HTML — NO se copian del output de la implementación.
Cada test que tiene un valor numérico crítico incluye el cálculo en comentario.

Regla anti-placebo: si refactorizamos la implementación y un test rompe, la
derivación en el comentario es la fuente de verdad — el código está mal, no
el test.

Cobertura:
    1. Helpers de redondeo half-up (vs banker's de round() Python).
    2. `_js_truthy_present` y `_js_number` (semántica JS).
    3. `_get_next_month_iso` (dec→ene, mes corriente).
    4. `_find_historical`, `_same_month_last_year_engine`.
    5. `_days_in_month`.
    6. `_avg_mom_growth` — window, count vs n, prev>0 guard, len<2.
    7. `_yoy_growth` — len<13, yearAgo ausente, yearAgo[field] falsy.
    8. `_has_yoy_data`, `_yoy_enabled`.
    9. `recompute_forecast_row` — overrides manual, availability clamp/scale,
       tacosTarget override, ventasPPC/tacos/salesVelocity, edge cases
       units=0/sessions=0/aov=0.
   10. `generate_forecast` — primera fila Dermaglos con horizon=6, momWindow=3,
       blend=50, seasonality OFF, yoy_mode='off' (derivación a mano abajo).
       Cobertura de ramas: blend MoM puro vs MoM+YoY; seasonality on vs off;
       historial insuficiente (<2, <12, <13).
   11. `auto_detect_seasonality` — patrón conocido (11 meses x 1000 + 1 mes
       x 2000), <12 → None, all-zero → indices neutros.

Diseño: tests puros sin runtime Streamlit. Llaman directamente al motor con
fixtures pequeños y la constante `_DERMAGLOS_DATA` del módulo.
"""

from __future__ import annotations

import math

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de redondeo half-up
# ─────────────────────────────────────────────────────────────────────────────

def test_round_half_up_int_basic():
    """Cubre el caso clásico .5 → round up (vs banker's de round() Python).

    Python `round(0.5)` = 0, `round(1.5)` = 2, `round(2.5)` = 2 (banker's).
    JS `Math.round(0.5)` = 1, `Math.round(1.5)` = 2, `Math.round(2.5)` = 3.
    Nuestro `_round_half_up_int` matchea JS para valores positivos.
    """
    assert rf._round_half_up_int(0.5) == 1
    assert rf._round_half_up_int(1.5) == 2
    assert rf._round_half_up_int(2.5) == 3  # banker's daría 2
    assert rf._round_half_up_int(3.5) == 4
    assert rf._round_half_up_int(541.1101) == 541
    assert rf._round_half_up_int(541.5) == 542
    assert rf._round_half_up_int(0) == 0
    assert rf._round_half_up_int(None) == 0


def test_round_half_up_dec_two_decimals():
    """Replica `Math.round(spend*100)/100` del HTML L1903.

    Ejemplos: 12.345 → 12.35 (NO 12.34 que daría banker's), 0.005 → 0.01.
    """
    # 12.345 * 100 = 1234.5 → Math.round → 1235 → /100 → 12.35
    assert rf._round_half_up_dec(12.345, 2) == 12.35
    # 0.005 * 100 = 0.5 → Math.round → 1 → /100 → 0.01
    assert rf._round_half_up_dec(0.005, 2) == 0.01
    # Caso AOV típico
    assert rf._round_half_up_dec(541.105, 2) == 541.11
    # 1 decimal — replica `+x.toFixed(1)` del HTML L1835
    assert rf._round_half_up_dec(30.05, 1) == 30.1
    assert rf._round_half_up_dec(30.04, 1) == 30.0
    # None / NaN → 0
    assert rf._round_half_up_dec(None) == 0.0
    assert rf._round_half_up_dec(float("nan")) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _js_truthy_present y _js_number
# ─────────────────────────────────────────────────────────────────────────────

def test_js_truthy_present():
    """Replica `v != null && v !== ''`. Crítico: 0 es TRUTHY (no '' ni None).

    El HTML usa esto para distinguir "el AM cargó 0 explícitamente" de "no
    cargó nada" — clave en spend/ventasPPC/manualRevenue/tacosTarget.
    """
    assert rf._js_truthy_present(0) is True       # 0 SÍ está presente
    assert rf._js_truthy_present(0.0) is True
    assert rf._js_truthy_present(1) is True
    assert rf._js_truthy_present(-1) is True
    assert rf._js_truthy_present("0") is True     # string "0" también
    assert rf._js_truthy_present(None) is False
    assert rf._js_truthy_present("") is False
    assert rf._js_truthy_present(float("nan")) is False


def test_js_number_conversion():
    """Replica `+v || 0` de JS. '', None, NaN, parse fail → 0."""
    assert rf._js_number(5) == 5.0
    assert rf._js_number(5.5) == 5.5
    assert rf._js_number("3.14") == 3.14
    assert rf._js_number("") == 0.0
    assert rf._js_number(None) == 0.0
    assert rf._js_number(float("nan")) == 0.0
    assert rf._js_number("not a number") == 0.0
    # 0 se preserva como 0 (no hace `|| 0` engaño porque +0 → 0, NaN no entra)
    assert rf._js_number(0) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _get_next_month_iso
# ─────────────────────────────────────────────────────────────────────────────

def test_get_next_month_iso_normal():
    """Mes corriente: 2025-04-01 → 2025-05-01."""
    assert rf._get_next_month_iso("2025-04-01") == "2025-05-01"
    assert rf._get_next_month_iso("2025-04-15") == "2025-05-01"  # día se reset a 01


def test_get_next_month_iso_year_rollover():
    """Diciembre → Enero del año siguiente."""
    assert rf._get_next_month_iso("2025-12-01") == "2026-01-01"
    assert rf._get_next_month_iso("2025-01-01") == "2025-02-01"


# ─────────────────────────────────────────────────────────────────────────────
# _find_historical y _same_month_last_year_engine
# ─────────────────────────────────────────────────────────────────────────────

def test_find_historical():
    rows = [
        {"date": "2024-01-01", "revenue": 100},
        {"date": "2024-02-01", "revenue": 200},
    ]
    assert rf._find_historical("2024-01-01", rows) == {"date": "2024-01-01", "revenue": 100}
    assert rf._find_historical("2024-03-01", rows) is None


def test_same_month_last_year_engine_found():
    rows = [
        {"date": "2024-06-01", "revenue": 500},
        {"date": "2024-07-01", "revenue": 600},
        {"date": "2025-06-01", "revenue": 700},
    ]
    # 2025-06-01 → busca 2024-06-01
    result = rf._same_month_last_year_engine("2025-06-01", rows)
    assert result == {"date": "2024-06-01", "revenue": 500}


def test_same_month_last_year_engine_not_found():
    rows = [{"date": "2025-06-01", "revenue": 700}]
    assert rf._same_month_last_year_engine("2025-06-01", rows) is None


# ─────────────────────────────────────────────────────────────────────────────
# _days_in_month
# ─────────────────────────────────────────────────────────────────────────────

def test_days_in_month():
    """Replica `new Date(Date.UTC(y, m+1, 0)).getUTCDate()` del HTML L1875."""
    assert rf._days_in_month("2025-01-15") == 31  # Enero
    assert rf._days_in_month("2025-02-01") == 28  # Feb 2025 no bisiesto
    assert rf._days_in_month("2024-02-15") == 29  # Feb 2024 bisiesto
    assert rf._days_in_month("2025-04-01") == 30  # Abril
    assert rf._days_in_month("2025-12-31") == 31  # Dic


# ─────────────────────────────────────────────────────────────────────────────
# _avg_mom_growth — port de avgMoMGrowth L1722
# ─────────────────────────────────────────────────────────────────────────────

def test_avg_mom_growth_simple():
    """3 valores [100, 110, 121] window=2.

    n = min(2, 3-1) = 2. Itera i de 1 a 2 (len-n=1, len=3 → range(1,3)).
    i=1: prev=h[0]=100, curr=h[1]=110 → (110-100)/100 = 0.10
    i=2: prev=h[1]=110, curr=h[2]=121 → (121-110)/110 = 0.1
    sum = 0.20, count=2 → avg = 0.10.
    """
    rows = [
        {"date": "2024-01-01", "revenue": 100},
        {"date": "2024-02-01", "revenue": 110},
        {"date": "2024-03-01", "revenue": 121},
    ]
    result = rf._avg_mom_growth("revenue", 2, rows)
    assert result == pytest.approx(0.10, rel=1e-9)


def test_avg_mom_growth_window_larger_than_len():
    """window=10 con 3 rows → n=min(10, 2)=2. Solo usa 2 transiciones."""
    rows = [
        {"date": "2024-01-01", "revenue": 100},
        {"date": "2024-02-01", "revenue": 110},
        {"date": "2024-03-01", "revenue": 121},
    ]
    # Mismo resultado que el test anterior por el clamp de n.
    assert rf._avg_mom_growth("revenue", 10, rows) == pytest.approx(0.10, rel=1e-9)


def test_avg_mom_growth_skips_zero_prev():
    """`prev > 0` guard: si prev es 0, la transición NO se cuenta.

    rows = [0, 100, 110, 121] window=3.
    n = min(3, 3) = 3. Itera i=1,2,3.
    i=1: prev=0 → SKIP. count NO incrementa.
    i=2: prev=100, curr=110 → 0.10.
    i=3: prev=110, curr=121 → 0.1.
    sum = 0.20, count=2 → avg = 0.10. NO se divide por 3.
    """
    rows = [
        {"date": "2024-01-01", "revenue": 0},
        {"date": "2024-02-01", "revenue": 100},
        {"date": "2024-03-01", "revenue": 110},
        {"date": "2024-04-01", "revenue": 121},
    ]
    assert rf._avg_mom_growth("revenue", 3, rows) == pytest.approx(0.10, rel=1e-9)


def test_avg_mom_growth_len_lt_2():
    """len < 2 → 0 (cortocircuito)."""
    assert rf._avg_mom_growth("revenue", 3, []) == 0.0
    assert rf._avg_mom_growth("revenue", 3, [{"date": "2024-01-01", "revenue": 100}]) == 0.0


def test_avg_mom_growth_all_zero_prevs():
    """Todos los prev son 0 → count=0 → return 0 (no div/0)."""
    rows = [
        {"date": "2024-01-01", "revenue": 0},
        {"date": "2024-02-01", "revenue": 0},
        {"date": "2024-03-01", "revenue": 100},
    ]
    # n=min(3,2)=2. i=1: prev=0 skip. i=2: prev=0 skip. count=0 → 0.0
    assert rf._avg_mom_growth("revenue", 3, rows) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _yoy_growth — port de yoyGrowth L1733
# ─────────────────────────────────────────────────────────────────────────────

def test_yoy_growth_lt_13():
    """len < 13 → 0."""
    rows = [{"date": f"2024-{m:02d}-01", "revenue": 100} for m in range(1, 13)]  # 12
    assert rf._yoy_growth("revenue", rows) == 0.0


def test_yoy_growth_normal():
    """13 meses: mes0=1000, mes12=1200, mismo mes-día un año después.

    last = h[-1] = 2025-01-01, revenue=1200.
    yearAgo iso = 2024-01-01, revenue=1000.
    (1200 - 1000) / 1000 = 0.20.
    """
    rows = [{"date": f"2024-{m:02d}-01", "revenue": 100} for m in range(1, 13)]
    # h[0]: 2024-01, h[12]: 2025-01
    rows[0]["revenue"] = 1000
    rows.append({"date": "2025-01-01", "revenue": 1200})
    assert rf._yoy_growth("revenue", rows) == pytest.approx(0.20, rel=1e-9)


def test_yoy_growth_year_ago_missing():
    """13 meses pero el row del año pasado NO está → 0.

    h[-1] = 2025-02-01 (sin el 2024-02-01 correspondiente).
    """
    rows = [{"date": f"2024-{m:02d}-01", "revenue": 100} for m in range(1, 13)]
    rows.append({"date": "2025-02-01", "revenue": 1200})
    # Verificamos que 2024-02-01 existe (mes 2) — entonces ese SÍ matchea.
    # Cambiamos last a 2025-13 — imposible. Usamos otro caso: borramos 2024-01.
    rows2 = [{"date": f"2024-{m:02d}-01", "revenue": 100} for m in range(2, 14)]
    # 12 entradas (2024-02 a 2025-01). Agregamos h[-1] = 2025-13 inválido?
    # Más simple: 13 filas pero sin match exacto del año anterior.
    rows3 = [{"date": f"2024-{m:02d}-15", "revenue": 100} for m in range(1, 13)]
    rows3.append({"date": "2025-01-20", "revenue": 1200})  # día 20, no 15
    assert rf._yoy_growth("revenue", rows3) == 0.0


def test_yoy_growth_year_ago_field_zero():
    """yearAgo existe pero revenue es 0/None → 0 (no div/0)."""
    rows = [{"date": f"2024-{m:02d}-01", "revenue": 100} for m in range(1, 13)]
    rows[0]["revenue"] = 0  # 2024-01-01 con revenue=0
    rows.append({"date": "2025-01-01", "revenue": 1200})
    assert rf._yoy_growth("revenue", rows) == 0.0


def test_has_yoy_data():
    assert rf._has_yoy_data([]) is False
    assert rf._has_yoy_data([{"date": "2024-01-01"}] * 12) is False
    assert rf._has_yoy_data([{"date": "2024-01-01"}] * 13) is True


def test_yoy_enabled_modes():
    """Cubre las 3 ramas de la línea L1768."""
    rows13 = [{"date": "2024-01-01"}] * 13
    rows12 = [{"date": "2024-01-01"}] * 12
    # 'on' siempre enabled, sin importar data.
    assert rf._yoy_enabled("on", rows12) is True
    assert rf._yoy_enabled("on", []) is True
    # 'auto' depende de hasYoYData.
    assert rf._yoy_enabled("auto", rows13) is True
    assert rf._yoy_enabled("auto", rows12) is False
    # 'off' siempre disabled.
    assert rf._yoy_enabled("off", rows13) is False


# ─────────────────────────────────────────────────────────────────────────────
# recompute_forecast_row — port de recomputeForecastRow L1873
# ─────────────────────────────────────────────────────────────────────────────

def test_recompute_row_basic():
    """Fila típica: revenueAuto=1000, aovAuto=50, sessionsAuto=2000,
    acosTarget=30, spend=100, sin manual overrides, availability default 100.

    Derivación:
      avail=100, avail_factor=1.0, revenue=1000*1.0=1000.
      aov=50 (Auto), sessions=2000 (Auto).
      units = 1000/50 = 20.
      cvr = (20/2000)*100 = 1.0.
      tacosTarget None → spend = +f.spend || 0 = 100.
      acos = 30 → ventasPPC = 100/(30/100) = 100/0.3 = 333.333...
      tacos = (100/1000)*100 = 10.0.
      pctVtasPPC = (333.333/1000)*100 = 33.333...
      dim = 31 (mayo) → salesVelocity = 20/31 = 0.6451...
    """
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 100,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
    }
    rf.recompute_forecast_row(f)
    assert f["revenue"] == pytest.approx(1000.0)
    assert f["units"] == pytest.approx(20.0)
    assert f["cvr"] == pytest.approx(1.0)
    assert f["ventasPPC"] == pytest.approx(333.3333333333333, rel=1e-9)
    assert f["tacos"] == pytest.approx(10.0)
    assert f["pctVtasPPC"] == pytest.approx(33.33333333333333, rel=1e-9)
    assert f["salesVelocity"] == pytest.approx(20.0 / 31.0, rel=1e-9)
    assert f["availability"] == 100.0


def test_recompute_row_availability_scales_revenue():
    """availability=50 → revenue *= 0.5 → 1000 * 0.5 = 500 → units 500/50 = 10.

    Sessions NO se escala (sigue 2000); cvr = (10/2000)*100 = 0.5.
    """
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 100,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
        "stockAvailability": 50,
    }
    rf.recompute_forecast_row(f)
    assert f["revenue"] == pytest.approx(500.0)
    assert f["units"] == pytest.approx(10.0)
    assert f["sessions"] == pytest.approx(2000.0)  # NO escala
    assert f["cvr"] == pytest.approx(0.5)
    assert f["availability"] == 50.0


def test_recompute_row_availability_clamp():
    """availability fuera de rango → clamp 0-100."""
    f_low = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 0,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
        "stockAvailability": -10,
    }
    rf.recompute_forecast_row(f_low)
    assert f_low["availability"] == 0.0
    assert f_low["revenue"] == 0.0
    assert f_low["units"] == 0.0

    f_high = dict(f_low)
    f_high["stockAvailability"] = 150
    rf.recompute_forecast_row(f_high)
    assert f_high["availability"] == 100.0
    assert f_high["revenue"] == 1000.0


def test_recompute_row_tacos_target_overrides_spend():
    """tacosTarget=15 con revenue=1000 → spend = 1000 * 15/100 = 150.

    f.spend se setea a 150 (half-up 2 dec). ventasPPC = 150/(30/100) = 500.
    """
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 100,  # va a ser pisado
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": 15,
    }
    rf.recompute_forecast_row(f)
    assert f["spend"] == pytest.approx(150.0)
    assert f["ventasPPC"] == pytest.approx(500.0)
    assert f["tacos"] == pytest.approx(15.0)  # 150/1000*100


def test_recompute_row_manual_revenue_override():
    """manualRevenue=2000 gana sobre revenueAuto=1000.

    revenue=2000*1.0=2000, units=2000/50=40, cvr=(40/2000)*100=2.0,
    tacos=(100/2000)*100=5.0, ventasPPC=100/0.3=333.333...
    """
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 100,
        "manualRevenue": 2000, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
    }
    rf.recompute_forecast_row(f)
    assert f["revenue"] == pytest.approx(2000.0)
    assert f["units"] == pytest.approx(40.0)
    assert f["cvr"] == pytest.approx(2.0)
    assert f["tacos"] == pytest.approx(5.0)


def test_recompute_row_units_zero_when_aov_zero():
    """aov=0 → units=0; sessions>0 pero units=0 → cvr=0."""
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 0, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 100,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
    }
    rf.recompute_forecast_row(f)
    assert f["units"] == 0.0
    assert f["cvr"] == 0.0


def test_recompute_row_cvr_zero_when_sessions_zero():
    """sessions=0 → cvr=0 (guard div/0)."""
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 0,
        "acosTarget": 30, "spend": 100,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
    }
    rf.recompute_forecast_row(f)
    assert f["cvr"] == 0.0


def test_recompute_row_acos_zero_means_no_ventas_ppc():
    """acos=0 → ventasPPC=0 (guard div/0)."""
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 0, "spend": 100,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": None,
    }
    rf.recompute_forecast_row(f)
    assert f["ventasPPC"] == 0.0
    assert f["acos"] == 0.0


def test_recompute_row_tacos_target_with_revenue_zero():
    """tacosTarget set pero revenue=0 (por manualRevenue=0 con availability 100) →
    `tacosTarget != null && revenue > 0` es False → cae al else, spend=+f.spend.
    """
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 77,
        "manualRevenue": 0, "manualAOV": None, "manualSessions": None,
        "tacosTarget": 15,
    }
    # manualRevenue=0 NO es _js_truthy_present (0 SÍ es truthy en _js_truthy_present!)
    # OJO: en _js_truthy_present, 0 es True. Entonces manualRevenue=0 SÍ gana →
    # revenue = 0. Y como revenue=0, tacosTarget no override → spend = 77.
    # ventasPPC = 77/(30/100) = 256.666...; tacos = 0 (rev=0).
    rf.recompute_forecast_row(f)
    assert f["revenue"] == 0.0
    assert f["spend"] == 77.0
    assert f["tacos"] == 0.0
    assert f["ventasPPC"] == pytest.approx(77.0 / 0.3, rel=1e-9)


def test_recompute_row_spend_half_up_rounding():
    """tacosTarget produce un spend con .005 → debe redondear half-up.

    revenue=2000, tacosTarget=15.005 (no típico pero válido):
    spend bruto = 2000 * 15.005 / 100 = 300.1 → half-up 2 dec → 300.1.
    Para forzar half-up usamos un valor que dé .005 exacto:
    revenue=200.1, tacosTarget=10 → 200.1 * 0.10 = 20.01 → 20.01.
    Más explícito: revenue=1000, tacosTarget=0.0005 → 0.005 → half-up → 0.01.
    """
    f = {
        "date": "2025-05-01",
        "revenueAuto": 1000, "aovAuto": 50, "sessionsAuto": 2000,
        "acosTarget": 30, "spend": 0,
        "manualRevenue": None, "manualAOV": None, "manualSessions": None,
        "tacosTarget": 0.0005,
    }
    rf.recompute_forecast_row(f)
    # 1000 * 0.0005/100 = 0.005 → half-up 2 dec → 0.01
    assert f["spend"] == 0.01


# ─────────────────────────────────────────────────────────────────────────────
# generate_forecast — fixture Dermaglos, primera fila derivada a mano
# ─────────────────────────────────────────────────────────────────────────────

# Constantes precomputadas para el primer forecast row con la fixture Dermaglos
# (23 meses jun-2024 a abr-2026), opts = {horizon: 6, momWindow: 3, blend: 50,
# useSeasonality: False}, seasonality OFF (default neutro), yoy_mode='off'.
#
# Derivación manual (los valores se computan con float64 estándar Python, NO se
# leen del output del motor — son la fuente de verdad):
#
#   rows[-3] = 2026-02-01  rev=5438.27  units=358  sessions=4231  cvr=8.46
#   rows[-2] = 2026-03-01  rev=5492.97  units=391  sessions=4261  cvr=9.18
#   rows[-1] = 2026-04-01  rev=5432.28  units=368  sessions=4522  cvr=8.14
#
#   gRev (window=3) over transitions i=20,21,22:
#     i=20: prev=rows[19].rev=5497.12, curr=5438.27
#           → (5438.27 - 5497.12) / 5497.12 = -0.010705157...
#     i=21: prev=5438.27, curr=5492.97
#           → (5492.97 - 5438.27) / 5438.27 = +0.010058676...
#     i=22: prev=5492.97, curr=5432.28
#           → (5432.28 - 5492.97) / 5492.97 = -0.011049404...
#     sum = -0.011695885... ; count=3 → gRev = -0.003898628...
#
#   gSess (window=3): same shape:
#     i=20: prev=rows[19].sess=5957, curr=4231 → -0.289743158...
#     i=21: prev=4231, curr=4261 → 0.007090995...
#     i=22: prev=4261, curr=4522 → 0.061253227...
#     sum = -0.221399, count=3 → gSess = -0.073799803...
#
#   prev = rows[-1] (2026-04-01)
#   yoy_enabled = False (yoy_mode='off') → rev_base = mom_proj.
#   mom_proj  = prev.rev * (1 + gRev) = 5432.28 * 0.996101372 = 5411.10148...
#   seasonality OFF → s_factor = 1 → revenue = 5411.10148...
#
#   mom_sess = 4522 * (1 - 0.073799803) = 4522 * 0.926200197 = 4188.27729...
#   sessions = mom_sess = 4188.27729...
#
#   avg_aov (last3, formula `r.rev/(r.units||1)`):
#     5438.27/358 = 15.19069832...
#     5492.97/391 = 14.04851662...
#     5432.28/368 = 14.76163043...
#     sum = 44.00084538..., avg = 14.66694846... (verificado float64)
#   units = revenue / avg_aov = 5411.10148 / 14.66694846 = 368.93164902...
#   cvr = (units/sessions)*100 = (368.93/4188.28)*100 = 8.80867296...
#
#   Spend defaults (Dermaglos NO trae spend/ventasPPC):
#     avg_tacos = None → tacos_use = 0.10
#     spend_default (pre-round) = revenue * 0.10 = 541.110148...
#     spend (Math.round) = 541
#   avg_acos_real = None → acos_default = 30.0
#
#   Después de recompute_forecast_row (availability default 100):
#     revenue = 5411.10148 (no escala)
#     spend = `+541 || 0` = 541
#     ventasPPC = 541 / (30/100) = 541 / 0.3 = 1803.33333...
#     tacos = (541 / 5411.10148) * 100 = 9.99796440...
#     pctVtasPPC = (1803.333 / 5411.10148) * 100 = 33.32654801...
#     dim (mayo 2026) = 31 → salesVelocity = 368.93 / 31 = 11.90102094...

_EXPECTED_FIRST_FORECAST = {
    "date": "2026-05-01",
    "year": 2026,
    "month": 4,  # mayo = índice 4 (0-based)
    "revenue": 5411.10148187,
    "sessions": 4188.27728928,
    "aov": 14.66694846,    # avg_aov del último trío Dermaglos (verificado float64)
    "units": 368.93164902,
    "cvr": 8.80867296,
    "spend": 541,
    "acosTarget": 30.0,
    "ventasPPC": 1803.33333333,
    "tacos": 9.99796440,
    "pctVtasPPC": 33.32654801,
    "salesVelocity": 11.90102094,
    "availability": 100.0,
    "seasonality": 1.0,
    "manualRevenue": None,
    "manualAOV": None,
    "manualSessions": None,
    "tacosTarget": None,
}


def _dermaglos_rows():
    """Fixture: 23 meses Dermaglos con spend/ventasPPC None (como _load_demo_into_active)."""
    return [{**r, "spend": None, "ventasPPC": None} for r in rf._DERMAGLOS_DATA]


def test_generate_forecast_first_row_dermaglos():
    """Primer forecast row con Dermaglos: derivación arriba en _EXPECTED_FIRST_FORECAST.

    Tolerancia rel=1e-6 para floats (suficiente para detectar drift de fórmula
    sin ser frágil con FP noise).
    """
    rows = _dermaglos_rows()
    opts = {"horizon": 6, "momWindow": 3, "blend": 50, "useSeasonality": False}
    seasonality = {"enabled": False, "indices": [1.0] * 12}
    fcs = rf.generate_forecast(opts, rows, seasonality, yoy_mode="off")
    assert len(fcs) == 6
    f0 = fcs[0]

    # Campos exactos.
    assert f0["date"] == _EXPECTED_FIRST_FORECAST["date"]
    assert f0["year"] == _EXPECTED_FIRST_FORECAST["year"]
    assert f0["month"] == _EXPECTED_FIRST_FORECAST["month"]
    assert f0["spend"] == _EXPECTED_FIRST_FORECAST["spend"]
    assert f0["acosTarget"] == _EXPECTED_FIRST_FORECAST["acosTarget"]
    assert f0["availability"] == _EXPECTED_FIRST_FORECAST["availability"]
    assert f0["seasonality"] == _EXPECTED_FIRST_FORECAST["seasonality"]
    assert f0["manualRevenue"] is None
    assert f0["manualAOV"] is None
    assert f0["manualSessions"] is None
    assert f0["tacosTarget"] is None

    # Floats con tolerancia.
    assert f0["revenue"] == pytest.approx(5411.10148187, rel=1e-6)
    assert f0["sessions"] == pytest.approx(4188.27728928, rel=1e-6)
    assert f0["aov"] == pytest.approx(14.66694846, rel=1e-6)
    assert f0["units"] == pytest.approx(368.93164902, rel=1e-6)
    assert f0["cvr"] == pytest.approx(8.80867296, rel=1e-6)
    assert f0["ventasPPC"] == pytest.approx(1803.33333333, rel=1e-6)
    assert f0["tacos"] == pytest.approx(9.99796440, rel=1e-6)
    assert f0["pctVtasPPC"] == pytest.approx(33.32654801, rel=1e-6)
    assert f0["salesVelocity"] == pytest.approx(11.90102094, rel=1e-6)


def test_generate_forecast_horizon_zero():
    """horizon=0 → lista vacía."""
    rows = _dermaglos_rows()
    opts = {"horizon": 0, "momWindow": 3, "blend": 50, "useSeasonality": False}
    fcs = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "off")
    assert fcs == []


def test_generate_forecast_empty_history():
    """rows vacío → lista vacía (cortocircuito antes del loop)."""
    opts = {"horizon": 6, "momWindow": 3, "blend": 50, "useSeasonality": False}
    fcs = rf.generate_forecast(opts, [], {"enabled": False, "indices": [1.0] * 12}, "auto")
    assert fcs == []


def test_generate_forecast_dates_advance_month_by_month():
    """horizon=6 sobre Dermaglos → fechas may, jun, jul, ago, sep, oct 2026."""
    rows = _dermaglos_rows()
    opts = {"horizon": 6, "momWindow": 3, "blend": 50, "useSeasonality": False}
    fcs = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "off")
    dates = [f["date"] for f in fcs]
    assert dates == [
        "2026-05-01", "2026-06-01", "2026-07-01",
        "2026-08-01", "2026-09-01", "2026-10-01",
    ]


def test_generate_forecast_yoy_on_changes_revenue():
    """Con yoy_mode='on' y >=13 meses, el primer forecast row debe diferir del
    primer row con yoy_mode='off' (porque rev_base = blend*momProj + (1-blend)*yoyProj
    cuando hay yoyMonth).

    No derivamos el número exacto YoY acá (ya cubierto el camino MoM en el test
    principal); solo verificamos que ON ≠ OFF para el mes que tiene YoY match.
    Dermaglos tiene jun-2024 → may-2025 → may-2026 (forecast). El mes forecast
    2026-05-01 busca 2025-05-01 → existe (rev=5354.91). yoy_enabled=True →
    blend=50% MoM, 50% YoY.

    Cálculo paralelo: yRev (revenue YoY) = (5432.28 - 5767.12)/5767.12 =
    -0.058061... yoyMonth.revenue = 5354.91. yoyProj = 5354.91*(1-0.058061) =
    5043.99... momProj (mismo gRev) = 5411.10148... blend=0.5 →
    rev_base = 0.5*5411.10148 + 0.5*5043.99 = 5227.55... que es DISTINTO al
    revenue del test OFF (5411.10148).
    """
    rows = _dermaglos_rows()
    opts = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": False}
    fcs_off = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "off")
    fcs_on = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "on")
    # MoM puro
    assert fcs_off[0]["revenue"] == pytest.approx(5411.10148187, rel=1e-6)
    # MoM + YoY blended — verificamos el cálculo exacto:
    #   yRev = (5432.28 - 5767.12)/5767.12 = -0.058061145...
    #   yoyMonth (2025-05-01).revenue = 5354.91
    #   yoyProj = 5354.91 * (1 + yRev) = 5354.91 * 0.941938855 = 5044.046...
    #   momProj = 5411.10148...
    #   rev_base = 0.5*5411.10148 + 0.5*5044.046 = 5227.57...
    # Como blend=0.5 puro
    expected_yoy_blend = 0.5 * 5411.10148187 + 0.5 * (5354.91 * (1 + (5432.28 - 5767.12) / 5767.12))
    assert fcs_on[0]["revenue"] == pytest.approx(expected_yoy_blend, rel=1e-6)
    assert fcs_off[0]["revenue"] != pytest.approx(fcs_on[0]["revenue"], rel=1e-4)


def test_generate_forecast_seasonality_on_scales_revenue():
    """seasonality enabled con un índice no-1 para el mes target escala revenue.

    Dermaglos forecast 2026-05-01 → mIdx = 4. Si seasonality.indices[4] = 1.5,
    revenue OFF * 1.5 = revenue ON.
    """
    rows = _dermaglos_rows()
    opts_off = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": False}
    opts_on = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": True}
    seas_off = {"enabled": False, "indices": [1.0] * 12}
    seas_on = {"enabled": True, "indices": [1.0] * 12}
    seas_on["indices"][4] = 1.5  # mayo
    fcs_off = rf.generate_forecast(opts_off, rows, seas_off, "off")
    fcs_on = rf.generate_forecast(opts_on, rows, seas_on, "off")
    # revenue ON = revenue OFF * 1.5
    assert fcs_on[0]["revenue"] == pytest.approx(fcs_off[0]["revenue"] * 1.5, rel=1e-9)
    # sessions también escala con el mismo factor
    assert fcs_on[0]["sessions"] == pytest.approx(fcs_off[0]["sessions"] * 1.5, rel=1e-9)
    assert fcs_on[0]["seasonality"] == 1.5


def test_generate_forecast_seasonality_use_flag_off_ignores_indices():
    """useSeasonality=False → indices se ignoran aunque enabled=True."""
    rows = _dermaglos_rows()
    opts = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": False}
    seas = {"enabled": True, "indices": [1.0] * 12}
    seas["indices"][4] = 1.5
    fcs = rf.generate_forecast(opts, rows, seas, "off")
    # s_factor = 1.0 igual (useSeason False corta antes)
    assert fcs[0]["seasonality"] == 1.0


def test_generate_forecast_seasonality_index_zero_falls_back_to_1():
    """`indices[mIdx] || 1` — si el índice es 0, usa 1 (replica el `|| 1` JS)."""
    rows = _dermaglos_rows()
    opts = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": True}
    seas = {"enabled": True, "indices": [1.0] * 12}
    seas["indices"][4] = 0  # mayo con índice 0 → debería caer a 1
    fcs = rf.generate_forecast(opts, rows, seas, "off")
    assert fcs[0]["seasonality"] == 1.0


def test_generate_forecast_history_lt_2_returns_baseline():
    """1 row de historia → gRev=0 → mom_proj = prev.revenue (sin crecimiento).

    Con 1 row, generate_forecast NO cortocircuita (la función solo lo hace si
    rows está vacío) — corre el loop normal con gRev=0.
    """
    rows = [{
        "date": "2025-01-01", "revenue": 1000, "units": 10,
        "sessions": 100, "cvr": 10.0, "spend": None, "ventasPPC": None,
    }]
    opts = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": False}
    fcs = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "off")
    assert len(fcs) == 1
    # gRev=0 → mom_proj = 1000 * 1 = 1000 → revenue ≈ 1000 (sin season ni avail).
    assert fcs[0]["revenue"] == pytest.approx(1000.0, rel=1e-9)
    assert fcs[0]["date"] == "2025-02-01"


def test_generate_forecast_history_lt_13_disables_yoy_in_auto():
    """yoy_mode='auto' con <13 rows → yoy_enabled=False → MoM puro (mismo que 'off')."""
    rows = _dermaglos_rows()[:12]  # 12 meses, no 13
    opts = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": False}
    fcs_auto = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "auto")
    fcs_off = rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "off")
    # Ambos en MoM puro → mismo revenue.
    assert fcs_auto[0]["revenue"] == pytest.approx(fcs_off[0]["revenue"], rel=1e-12)


def test_generate_forecast_mutation_safe_on_input_rows():
    """generate_forecast NO debe mutar la lista de input rows."""
    rows = _dermaglos_rows()
    snapshot = [dict(r) for r in rows]
    opts = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": False}
    rf.generate_forecast(opts, rows, {"enabled": False, "indices": [1.0] * 12}, "auto")
    assert rows == snapshot  # sin mutación in-place


# ─────────────────────────────────────────────────────────────────────────────
# auto_detect_seasonality — port de autoDetectSeasonality L2266
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_detect_seasonality_lt_12_returns_none():
    """len < 12 → None (el HTML hace alert(); acá la UI maneja el mensaje)."""
    rows = [{"date": f"2024-{m:02d}-01", "revenue": 100} for m in range(1, 12)]  # 11
    assert rf.auto_detect_seasonality(rows) is None


def test_auto_detect_seasonality_known_pattern():
    """11 meses x 1000 + 1 mes x 2000 (diciembre) → índice diciembre alto.

    sums por month-of-year (índice 0=Ene...11=Dic):
      0..10 → 1000, count=1
      11    → 2000, count=1
    avgPerMonth = [1000, 1000, ..., 1000, 2000]
    overall = sum / count(meses con avg>0) = (11*1000 + 2000) / 12 = 13000/12 = 1083.333...
    indices:
      0..10 → 1000/1083.333 = 0.923076923... → half-up 3 dec → 0.923
      11    → 2000/1083.333 = 1.846153846... → half-up 3 dec → 1.846
    """
    rows = []
    for m in range(1, 13):  # Ene..Dic 2024
        rev = 2000 if m == 12 else 1000
        rows.append({"date": f"2024-{m:02d}-01", "revenue": rev})
    result = rf.auto_detect_seasonality(rows)
    assert result is not None
    assert result["enabled"] is True
    assert len(result["indices"]) == 12
    # 11 primeros índices con valor 0.923 (1000/1083.333 redondeado 3 dec).
    for i in range(11):
        assert result["indices"][i] == 0.923, f"índice {i} esperaba 0.923, obtuvo {result['indices'][i]}"
    # Diciembre = índice 11 → 1.846.
    assert result["indices"][11] == 1.846


def test_auto_detect_seasonality_zero_month_keeps_neutral():
    """Si un mes tiene avgPerMonth=0 (no hay datos de ese mes), su índice queda 1.

    12 rows pero solo 11 meses distintos (jul aparece 2 veces, ago no):
      jul2024, jul2025 → mes 6 (índice JS) con count=2
      ago no aparece → mes 7 con count=0 → avgPerMonth[7]=0 → indices[7]=1
    """
    rows = [
        {"date": "2024-01-01", "revenue": 100},
        {"date": "2024-02-01", "revenue": 100},
        {"date": "2024-03-01", "revenue": 100},
        {"date": "2024-04-01", "revenue": 100},
        {"date": "2024-05-01", "revenue": 100},
        {"date": "2024-06-01", "revenue": 100},
        {"date": "2024-07-01", "revenue": 100},
        {"date": "2025-07-01", "revenue": 200},  # 2do julio
        {"date": "2024-09-01", "revenue": 100},
        {"date": "2024-10-01", "revenue": 100},
        {"date": "2024-11-01", "revenue": 100},
        {"date": "2024-12-01", "revenue": 100},
    ]
    result = rf.auto_detect_seasonality(rows)
    assert result is not None
    # Agosto (índice 7) → 1.0 por el `a > 0 else 1`.
    assert result["indices"][7] == 1.0
    # Julio (índice 6) → avg(100, 200)/2 = 150; los demás meses con data tienen 100.
    # avg_per_month = [100, 100, 100, 100, 100, 100, 150, 0, 100, 100, 100, 100].
    # months_with_data = 11 (todos menos agosto que es 0).
    # sum(avg_per_month) = (Ene..Jun) 6*100 + julio 150 + agosto 0 + (Sep..Dic) 4*100
    #                    = 600 + 150 + 0 + 400 = 1150.
    # overall = 1150 / 11 = 104.545454...
    # idx[6] = 150 / 104.545 = 1.434782... → half-up 3 dec → 1.435.
    assert result["indices"][6] == pytest.approx(1.435, abs=0.001)


def test_auto_detect_seasonality_all_zero_safe():
    """Defensivo: si todos los meses tienen revenue=0, overall sería 0/0 — el
    HTML no contempla esto (alert() solo bloquea por len, no por valores). Acá
    devolvemos indices neutros + enabled=True para no romper el wiring del state.
    """
    rows = [{"date": f"2024-{m:02d}-01", "revenue": 0} for m in range(1, 13)]
    result = rf.auto_detect_seasonality(rows)
    assert result is not None
    assert result["indices"] == [1.0] * 12
    assert result["enabled"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper Streamlit → motor puro
# ─────────────────────────────────────────────────────────────────────────────

def test_run_forecast_for_active_client_writes_to_state():
    """El wrapper lee del accessor, llama al motor, MUTA cur['forecast']."""
    state = {
        rf._K_CLIENTS: [rf._new_client(name="Test", client_id="test-id")],
        rf._K_ACTIVE_CLIENT_ID: "test-id",
        rf._K_ACCOUNT_MANAGERS: [],
    }
    # Cargar histórico Dermaglos en el cliente.
    state[rf._K_CLIENTS][0]["historical"] = _dermaglos_rows()
    state[rf._K_CLIENTS][0]["yoy_mode"] = "off"

    opts = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": False}
    result = rf._run_forecast_for_active_client(opts, state=state)
    assert len(result) == 3
    # Mutación in-place: cur['forecast'] tiene lo mismo.
    assert state[rf._K_CLIENTS][0]["forecast"] == result


def test_run_forecast_for_active_client_no_active():
    """Sin cliente activo → lista vacía, sin error."""
    state = {
        rf._K_CLIENTS: [],
        rf._K_ACTIVE_CLIENT_ID: None,
        rf._K_ACCOUNT_MANAGERS: [],
    }
    opts = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": False}
    result = rf._run_forecast_for_active_client(opts, state=state)
    assert result == []

"""Tests B1c — resolver "esto pasó / esto proyecté" de un mes, para el dashboard.

`_month_actual` y `_month_forecast` son funciones puras (sin UI, sin
session_state) que el dashboard global va a consumir en el bloque 2.

Regla del actual: si el mes existe en `historical` CON spend cargado, ese es el
actual; si no, se busca en `actual`. El AM no debe cargar el mismo número dos
veces: los meses cerrados ya los carga en historical.

Regla del forecast: sale del snapshot BASELINE, nunca del forecast vivo. Sin
baseline, o con un baseline que no cubre el mes, no hay número: un denominador
inventado es peor que una celda vacía.
"""
from __future__ import annotations

import math

import pytest

from modules.pages import revenue_forecast as rf


_ACTUAL_KEYS = {"revenue", "ventasPPC", "spend", "acos", "tacos", "partial", "source"}
_FORECAST_KEYS = {
    "revenue", "ventasPPC", "spend", "acos", "tacos", "source",
    "snapshot_name", "snapshot_created_at",
}


def _row(date: str, revenue=1000.0, spend=None, ventas_ppc=None, **extra) -> dict:
    return {"date": date, "revenue": revenue, "units": 10, "sessions": 300,
            "cvr": 3.3, "spend": spend, "ventasPPC": ventas_ppc, **extra}


def _client(historical=None, actual=None) -> dict:
    cur = rf._new_client(name="T", client_id="t1")
    cur["historical"] = historical or []
    cur["actual"] = actual or []
    return cur


# ─────────────────────────────────────────────────────────────────────────────
# _month_actual — prioridad entre capas
# ─────────────────────────────────────────────────────────────────────────────

def test_historical_con_spend_gana_sobre_actual_mismo_mes():
    cur = _client(
        historical=[_row("2026-07-01", revenue=5000.0, spend=500.0, ventas_ppc=2000.0)],
        actual=[_row("2026-07-01", revenue=4800.0, spend=10.0, ventas_ppc=20.0,
                     partial=True, days_covered=31)],
    )
    m = rf._month_actual(cur, "2026-07")
    assert m["source"] == "historical"
    assert m["revenue"] == 5000.0
    assert m["spend"] == 500.0
    assert m["ventasPPC"] == 2000.0
    assert m["partial"] is False
    assert set(m.keys()) == _ACTUAL_KEYS


@pytest.mark.parametrize("sin_dato", [None, "", float("nan")])
def test_historical_sin_spend_cae_a_actual(sin_dato):
    """None, '' y NaN son los tres "sin dato" — el mismo criterio que
    `_update_actual_row`. Un NaN que contara como spend cargado haría ganar a
    historical con un denominador roto."""
    cur = _client(
        historical=[_row("2026-07-01", revenue=5000.0, spend=sin_dato, ventas_ppc=300.0)],
        actual=[_row("2026-07-01", revenue=4800.0, spend=90.0, ventas_ppc=360.0,
                     partial=True, days_covered=12)],
    )
    m = rf._month_actual(cur, "2026-07")
    assert m["source"] == "actual"
    assert m["revenue"] == 4800.0
    assert m["spend"] == 90.0
    assert m["partial"] is True


def test_historical_con_spend_sin_ventas_ppc_sigue_ganando():
    """El AM cargó el gasto y todavía no las ventas PPC: el mes ya está
    declarado cerrado. NO se cae a actual por un campo faltante."""
    cur = _client(
        historical=[_row("2026-07-01", revenue=5000.0, spend=500.0, ventas_ppc=None)],
        actual=[_row("2026-07-01", revenue=4800.0, spend=90.0, ventas_ppc=360.0,
                     partial=False)],
    )
    m = rf._month_actual(cur, "2026-07")
    assert m["source"] == "historical"
    assert m["spend"] == 500.0
    assert m["ventasPPC"] is None
    assert m["acos"] is None
    assert m["tacos"] == 10.0


def test_mes_solo_en_actual_respeta_partial():
    cur = _client(actual=[
        _row("2026-06-01", spend=50.0, partial=False, days_covered=30),
        _row("2026-07-01", spend=60.0, partial=True, days_covered=12),
    ])
    jun = rf._month_actual(cur, "2026-06")
    jul = rf._month_actual(cur, "2026-07")
    assert (jun["source"], jun["partial"]) == ("actual", False)
    assert (jul["source"], jul["partial"]) == ("actual", True)


def test_mes_solo_en_actual_partial_desconocido_queda_none():
    """BR mensual: la cobertura es desconocida. La función es pura y no la
    resuelve contra hoy (eso es `_resolve_partial`)."""
    cur = _client(actual=[_row("2026-07-01", spend=60.0, partial=None)])
    assert rf._month_actual(cur, "2026-07")["partial"] is None


def test_mes_en_ninguna_capa_devuelve_none():
    cur = _client(
        historical=[_row("2026-05-01", spend=1.0)],
        actual=[_row("2026-06-01", spend=1.0)],
    )
    assert rf._month_actual(cur, "2026-07") is None


def test_mes_en_historical_sin_spend_y_ausente_en_actual_sale_de_historical():
    """El revenue del mes es un dato real: devolver None diría "no hay dato".
    Sale de historical con spend None y los ratios en None."""
    cur = _client(historical=[_row("2026-07-01", revenue=5000.0, spend=None)])
    m = rf._month_actual(cur, "2026-07")
    assert m["source"] == "historical"
    assert m["revenue"] == 5000.0
    assert m["spend"] is None
    assert m["ventasPPC"] is None
    assert m["acos"] is None and m["tacos"] is None
    assert m["partial"] is False


def test_cliente_sin_key_actual_no_rompe():
    cur = _client(historical=[_row("2026-07-01", spend=None)])
    del cur["actual"]
    assert rf._month_actual(cur, "2026-07")["source"] == "historical"
    assert rf._month_actual(cur, "2026-08") is None


# ─────────────────────────────────────────────────────────────────────────────
# _month_actual — ratios y normalización
# ─────────────────────────────────────────────────────────────────────────────

def test_acos_y_tacos_calculados():
    cur = _client(historical=[_row("2026-07-01", revenue=4000.0, spend=200.0,
                                   ventas_ppc=800.0)])
    m = rf._month_actual(cur, "2026-07")
    assert m["acos"] == 25.0    # 200 / 800 * 100
    assert m["tacos"] == 5.0    # 200 / 4000 * 100


def test_acos_none_con_ventas_ppc_cero():
    cur = _client(actual=[_row("2026-07-01", revenue=4000.0, spend=200.0,
                               ventas_ppc=0.0, partial=True)])
    m = rf._month_actual(cur, "2026-07")
    assert m["acos"] is None
    assert m["ventasPPC"] == 0.0     # cero es un dato
    assert m["tacos"] == 5.0


def test_tacos_none_con_revenue_cero():
    cur = _client(actual=[_row("2026-07-01", revenue=0.0, spend=200.0,
                               ventas_ppc=800.0, partial=False)])
    m = rf._month_actual(cur, "2026-07")
    assert m["tacos"] is None
    assert m["acos"] == 25.0


def test_ventas_ppc_sin_dato_sale_none_en_actual():
    for sin_dato in (None, "", float("nan")):
        cur = _client(actual=[_row("2026-07-01", spend=100.0, ventas_ppc=sin_dato,
                                   partial=True)])
        m = rf._month_actual(cur, "2026-07")
        assert m["ventasPPC"] is None
        assert m["acos"] is None


def test_period_acepta_yyyy_mm_y_rechaza_basura():
    cur = _client(historical=[_row("2026-07-01", spend=1.0)])
    assert rf._month_actual(cur, "2026-07")["source"] == "historical"
    assert rf._month_actual(cur, "2026-07-01")["source"] == "historical"
    for bad in ("", "julio", "2026-7", "2026-13", None):
        assert rf._month_actual(cur, bad) is None


def test_valores_son_float_no_string():
    cur = _client(historical=[_row("2026-07-01", revenue=5000, spend="500",
                                   ventas_ppc=2000)])
    m = rf._month_actual(cur, "2026-07")
    assert isinstance(m["spend"], float) and m["spend"] == 500.0
    assert isinstance(m["revenue"], float)


# ─────────────────────────────────────────────────────────────────────────────
# _month_forecast
# ─────────────────────────────────────────────────────────────────────────────

_ABSENT = object()


def _fc(date: str, revenue: float, spend, ventas_ppc,
        acos=_ABSENT, tacos=_ABSENT) -> dict:
    """Fila de forecast. acos/tacos sólo se incluyen si se pasan: sin ellos la
    fila ejercita el fallback de cálculo."""
    row = {"date": date, "revenue": revenue, "spend": spend,
           "ventasPPC": ventas_ppc}
    if acos is not _ABSENT:
        row["acos"] = acos
    if tacos is not _ABSENT:
        row["tacos"] = tacos
    return row


def _client_with_baseline(forecast_rows: list, name="Plan Q4") -> dict:
    cur = _client()
    cur["forecast"] = forecast_rows
    snap = rf._save_forecast_snapshot(cur, name, {"horizon": len(forecast_rows)})
    rf._set_baseline_snapshot(cur, snap["id"])
    return cur


def test_month_forecast_sin_baseline_devuelve_none():
    cur = _client()
    cur["forecast"] = [_fc("2026-10-01", 9000.0, 900.0, 3000.0)]
    rf._save_forecast_snapshot(cur, "No oficial", {})
    assert rf._month_forecast(cur, "2026-10") is None


def test_month_forecast_baseline_no_cubre_el_mes_devuelve_none():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, 3000.0)])
    # El forecast VIVO sí cubre noviembre: no se cae a él.
    cur["forecast"] = [_fc("2026-11-01", 9500.0, 950.0, 3100.0)]
    assert rf._month_forecast(cur, "2026-11") is None


def test_month_forecast_lee_del_baseline_no_del_forecast_vivo():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, 3000.0)])
    cur["forecast"] = [_fc("2026-10-01", 1.0, 1.0, 1.0)]
    m = rf._month_forecast(cur, "2026-10")
    assert m["revenue"] == 9000.0


def test_month_forecast_devuelve_snapshot_name_y_created_at():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, 3000.0)],
                                name="Plan Q4")
    snap = rf._get_baseline_snapshot(cur)
    m = rf._month_forecast(cur, "2026-10")
    assert set(m.keys()) == _FORECAST_KEYS
    assert m["snapshot_name"] == "Plan Q4"
    assert m["snapshot_created_at"] == snap["created_at"]
    assert m["source"] == "baseline"


def test_month_forecast_metricas_y_ratios():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, 3000.0)])
    m = rf._month_forecast(cur, "2026-10")
    assert m["revenue"] == 9000.0
    assert m["spend"] == 900.0
    assert m["ventasPPC"] == 3000.0
    assert m["acos"] == 30.0            # 900 / 3000 * 100
    assert m["tacos"] == 10.0           # 900 / 9000 * 100


def test_month_forecast_ratios_none_con_divisor_cero():
    cur = _client_with_baseline([_fc("2026-10-01", 0.0, 900.0, 0.0)])
    m = rf._month_forecast(cur, "2026-10")
    assert m["acos"] is None and m["tacos"] is None


def test_month_forecast_spend_sin_dato_da_ratios_none():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, None, 0.0)])
    m = rf._month_forecast(cur, "2026-10")
    assert m["spend"] is None
    assert m["acos"] is None and m["tacos"] is None


def test_month_forecast_toggle_quita_el_baseline():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, 3000.0)])
    rf._set_baseline_snapshot(cur, rf._get_baseline_snapshot(cur)["id"])
    assert rf._month_forecast(cur, "2026-10") is None


def test_month_forecast_period_invalido_devuelve_none():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, 3000.0)])
    assert rf._month_forecast(cur, "octubre") is None
    assert not math.isnan(rf._month_forecast(cur, "2026-10")["revenue"])


# ─────────────────────────────────────────────────────────────────────────────
# Commit 5 — ACOS/TACOS del forecast se LEEN de la fila (coherencia con F6.3c)
# ─────────────────────────────────────────────────────────────────────────────
#
# El motor escribe f["acos"] / f["tacos"] respetando los overrides acosTarget /
# tacosTarget del AM, y la tabla y el chart de M31 los leen. Recalcular desde
# spend/ventasPPC es el bug F6.3c (ver `_acos_tacos_chart`).

def test_month_forecast_acos_de_la_fila_gana_sobre_el_calculo():
    """EL test: spend/ventasPPC darían 90%, el AM fijó 15%. Sale 15."""
    cur = _client_with_baseline([
        _fc("2026-10-01", 9000.0, 900.0, 1000.0, acos=15.0, tacos=10.0),
    ])
    m = rf._month_forecast(cur, "2026-10")
    assert m["acos"] == 15.0
    assert m["acos"] != 900.0 / 1000.0 * 100


def test_month_forecast_acos_cero_de_la_fila_es_dato():
    """Sin acosTarget el motor escribe 0.0; eso es lo que ve el AM en la tabla."""
    cur = _client_with_baseline([
        _fc("2026-10-01", 9000.0, 900.0, 1000.0, acos=0.0),
    ])
    assert rf._month_forecast(cur, "2026-10")["acos"] == 0.0


@pytest.mark.parametrize("sin_acos", [_ABSENT, None, "", float("nan")])
def test_month_forecast_sin_acos_cae_al_calculo(sin_acos):
    cur = _client_with_baseline([
        _fc("2026-10-01", 9000.0, 900.0, 3000.0, acos=sin_acos),
    ])
    assert rf._month_forecast(cur, "2026-10")["acos"] == 30.0   # 900 / 3000


def test_month_forecast_sin_acos_y_sin_ventas_ppc_da_none():
    cur = _client_with_baseline([_fc("2026-10-01", 9000.0, 900.0, None)])
    assert rf._month_forecast(cur, "2026-10")["acos"] is None


def test_month_forecast_tacos_de_la_fila_gana_sobre_el_calculo():
    """Override tacosTarget 8.33: el motor redondea el spend y el cálculo da
    otro número. Sale el de la fila."""
    cur = _client_with_baseline([
        _fc("2026-10-01", 9000.0, 900.0, 3000.0, tacos=8.33),
    ])
    m = rf._month_forecast(cur, "2026-10")
    assert m["tacos"] == 8.33
    assert m["tacos"] != 900.0 / 9000.0 * 100


@pytest.mark.parametrize("sin_tacos", [_ABSENT, None, "", float("nan")])
def test_month_forecast_sin_tacos_cae_al_calculo(sin_tacos):
    cur = _client_with_baseline([
        _fc("2026-10-01", 9000.0, 900.0, 3000.0, tacos=sin_tacos),
    ])
    assert rf._month_forecast(cur, "2026-10")["tacos"] == 10.0  # 900 / 9000


def test_month_forecast_sin_tacos_y_sin_revenue_da_none():
    cur = _client_with_baseline([_fc("2026-10-01", None, 900.0, 3000.0)])
    assert rf._month_forecast(cur, "2026-10")["tacos"] is None


def test_month_actual_ignora_acos_tacos_basura_de_la_fila():
    """No-regresión: el real se CALCULA desde el gasto que pasó. Una key
    acos/tacos en la fila (basura) no se lee."""
    cur = _client(
        historical=[_row("2026-07-01", revenue=4000.0, spend=200.0,
                         ventas_ppc=800.0, acos=999.0, tacos=-5.0)],
        actual=[_row("2026-08-01", revenue=2000.0, spend=100.0,
                     ventas_ppc=400.0, partial=True, acos=777.0, tacos=123.0)],
    )
    jul = rf._month_actual(cur, "2026-07")
    ago = rf._month_actual(cur, "2026-08")
    assert (jul["acos"], jul["tacos"]) == (25.0, 5.0)
    assert (ago["acos"], ago["tacos"]) == (25.0, 5.0)

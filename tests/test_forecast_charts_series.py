"""M31 G1 — Tests de los helpers puros de series para charts.

Scope acotado a la sección F6-G1 de `revenue_forecast.py`: `_safe_num`,
`_shift_period`, los accessors hist/fc del catálogo `_METRICS`, `_series`,
`_bridge` (el helper central) y `_yoy_series`. NADA de Streamlit, NADA de Plotly,
CERO fixtures reales, CERO skip guards — 100% puros.

Invariantes load-bearing que blindan bugs que ya nos mordieron:
  - `_safe_num`: None/''/NaN → None (hueco), NUNCA 0 (NaN es truthy en Python).
  - fc accessors LEEN el campo (respetan overrides acosTarget/tacosTarget del AM),
    NO recalculan (sería el bug F6.3c: chart ≠ tabla).
  - `_bridge`: la serie fc arranca en el último punto histórico (from_hist).
  - `_yoy_series`: la fuente es SIEMPRE hist_rows + from_hist, nunca el forecast.
"""

from __future__ import annotations

import math

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# _safe_num
# ─────────────────────────────────────────────────────────────────────────────

def test_safe_num_none_is_none():
    assert rf._safe_num(None) is None


def test_safe_num_empty_string_is_none():
    assert rf._safe_num("") is None
    assert rf._safe_num("   ") is None


def test_safe_num_nan_is_none():
    assert rf._safe_num(float("nan")) is None


def test_safe_num_zero_is_zero_not_none():
    assert rf._safe_num(0) == 0.0
    assert rf._safe_num(0) is not None
    assert rf._safe_num(0.0) == 0.0


def test_safe_num_comma_decimal():
    assert rf._safe_num("1,234.5") == 1234.5


def test_safe_num_currency():
    assert rf._safe_num("$1,234") == 1234.0


def test_safe_num_percent():
    assert rf._safe_num("12%") == 12.0


def test_safe_num_plain_float():
    assert rf._safe_num(987.6) == 987.6


# ─────────────────────────────────────────────────────────────────────────────
# _shift_period
# ─────────────────────────────────────────────────────────────────────────────

def test_shift_period_minus_12_crossing_year():
    assert rf._shift_period("2026-03-01", -12) == "2025-03-01"


def test_shift_period_minus_12_from_january():
    assert rf._shift_period("2026-01-01", -12) == "2025-01-01"


def test_shift_period_plus_1_from_december():
    assert rf._shift_period("2026-12-01", 1) == "2027-01-01"


# ─────────────────────────────────────────────────────────────────────────────
# _days_in_month (reusado del módulo)
# ─────────────────────────────────────────────────────────────────────────────

def test_days_in_month_feb_leap():
    assert rf._days_in_month("2024-02-01") == 29


def test_days_in_month_feb_nonleap():
    assert rf._days_in_month("2025-02-01") == 28


def test_days_in_month_april():
    assert rf._days_in_month("2026-04-01") == 30


# ─────────────────────────────────────────────────────────────────────────────
# _bridge — el helper central
# ─────────────────────────────────────────────────────────────────────────────

def _hist(date, **kw):
    base = {"date": date, "revenue": 0.0, "units": 0.0, "sessions": 0.0}
    base.update(kw)
    return base


def _fc(date, **kw):
    base = {"date": date, "revenue": 0.0, "units": 0.0, "sessions": 0.0, "aov": 0.0}
    base.update(kw)
    return base


def test_bridge_fc_starts_at_last_hist_point():
    hist = [_hist("2026-05-01", revenue=1000.0), _hist("2026-06-01", revenue=1100.0)]
    fc = [_fc("2026-07-01", revenue=1200.0), _fc("2026-08-01", revenue=1300.0)]
    from_hist = rf._reader("revenue")
    from_fc = rf._reader("revenue")
    sh, sf = rf._bridge(hist, fc, from_hist, from_fc)
    assert sf["x"][0] == sh["x"][-1] == "2026-06-01"
    assert sf["y"][0] == sh["y"][-1] == 1100.0


def test_bridge_fc_length_is_plus_one():
    hist = [_hist("2026-05-01"), _hist("2026-06-01")]
    fc = [_fc("2026-07-01"), _fc("2026-08-01"), _fc("2026-09-01")]
    acc = rf._reader("revenue")
    _, sf = rf._bridge(hist, fc, acc, acc)
    assert len(sf["x"]) == len(fc) + 1
    assert len(sf["y"]) == len(fc) + 1


def test_bridge_no_hist_no_bridge():
    fc = [_fc("2026-07-01"), _fc("2026-08-01")]
    acc = rf._reader("revenue")
    sh, sf = rf._bridge([], fc, acc, acc)
    assert sh == {"x": [], "y": []}
    assert len(sf["x"]) == len(fc)   # sin bridge


def test_bridge_empty_forecast():
    hist = [_hist("2026-05-01", revenue=1000.0)]
    acc = rf._reader("revenue")
    sh, sf = rf._bridge(hist, [], acc, acc)
    assert sf == {"x": [], "y": []}
    assert sh["y"] == [1000.0]


def test_bridge_none_last_hist_value_copies_none():
    # spend ausente en la última hist row → from_hist devuelve None → bridge None.
    hist = [_hist("2026-05-01", spend=500.0), _hist("2026-06-01")]  # 2da sin spend
    fc = [_fc("2026-07-01", spend=600.0)]
    from_hist = rf._reader("spend")
    from_fc = rf._reader("spend")
    sh, sf = rf._bridge(hist, fc, from_hist, from_fc)
    assert sh["y"][-1] is None
    assert sf["y"][0] is None   # NO inventa valor


# ─────────────────────────────────────────────────────────────────────────────
# Accessors — blindaje del bug de shape hist vs fc
# ─────────────────────────────────────────────────────────────────────────────

def test_hist_aov_computed_from_revenue_units():
    acc = rf._METRICS["aov"]["from_hist"]
    assert acc({"date": "2026-05-01", "revenue": 1000.0, "units": 50.0}) == 20.0


def test_fc_aov_read_not_computed():
    # aov del campo (12.0) distinto de revenue/units (=20.0) → gana el CAMPO.
    acc = rf._METRICS["aov"]["from_fc"]
    row = {"date": "2026-07-01", "revenue": 1000.0, "units": 50.0, "aov": 12.0}
    assert acc(row) == 12.0   # override del AM, NO el cálculo


def test_fc_acos_read_not_computed():
    # acos del campo (15) distinto de spend/ventasPPC*100 (=30) → gana el CAMPO.
    acc = rf._METRICS["acos"]["from_fc"]
    row = {"date": "2026-07-01", "spend": 300.0, "ventasPPC": 1000.0, "acos": 15.0}
    assert acc(row) == 15.0   # respeta acosTarget, NO recalcula


def test_hist_acos_computed_with_guards():
    acc = rf._METRICS["acos"]["from_hist"]
    row = {"date": "2026-05-01", "spend": 300.0, "ventasPPC": 1000.0}
    assert acc(row) == 30.0   # 300/1000*100


def test_hist_spend_empty_string_is_none():
    acc = rf._METRICS["spend"]["from_hist"]
    assert acc({"date": "2026-05-01", "spend": ""}) is None


def test_hist_acos_zero_ventasppc_is_none():
    acc = rf._METRICS["acos"]["from_hist"]
    # denominador 0 → None, NO inf, NO ZeroDivisionError.
    assert acc({"date": "2026-05-01", "spend": 300.0, "ventasPPC": 0.0}) is None


def test_hist_sales_velocity_respects_month_length():
    acc = rf._METRICS["salesVelocity"]["from_hist"]
    # feb 2025 = 28 días. 280 units / 28 = 10.0.
    assert acc({"date": "2025-02-01", "units": 280.0}) == 10.0
    # abr = 30 días. 300 / 30 = 10.0.
    assert acc({"date": "2026-04-01", "units": 300.0}) == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# _yoy_series
# ─────────────────────────────────────────────────────────────────────────────

def _year_hist(start_year=2025):
    """13 meses: ene-2025 .. ene-2026, revenue incremental."""
    rows = []
    for i in range(13):
        y = start_year + (i // 12)
        m = (i % 12) + 1
        rows.append({"date": f"{y:04d}-{m:02d}-01", "revenue": 1000.0 + i * 100})
    return rows


def test_yoy_axis_is_hist_plus_fc():
    hist = [{"date": "2025-01-01", "revenue": 100.0}, {"date": "2025-02-01", "revenue": 200.0}]
    fc = [{"date": "2025-03-01", "revenue": 300.0}]
    s = rf._yoy_series(hist, fc, rf._reader("revenue"))
    assert s["x"] == ["2025-01-01", "2025-02-01", "2025-03-01"]


def test_yoy_matches_exact_minus_12_months():
    hist = _year_hist()  # ene-2025..ene-2026
    fc = []
    s = rf._yoy_series(hist, fc, rf._reader("revenue"))
    # 2026-01 (index 12) mira 2025-01 (index 0, revenue 1000).
    idx = s["x"].index("2026-01-01")
    assert s["y"][idx] == 1000.0
    # 2025-01 no tiene 2024-01 → None.
    assert s["y"][s["x"].index("2025-01-01")] is None


def test_yoy_under_12_months_all_none():
    hist = [{"date": "2026-05-01", "revenue": 1.0}, {"date": "2026-06-01", "revenue": 2.0}]
    s = rf._yoy_series(hist, [], rf._reader("revenue"))
    assert s["x"] == ["2026-05-01", "2026-06-01"]
    assert all(v is None for v in s["y"])   # lista alineada, no vacía


def test_yoy_gap_in_history_yields_none_at_that_point():
    # 2025-03 falta → 2026-03 no encuentra match → None.
    hist = [
        {"date": "2025-01-01", "revenue": 100.0},
        {"date": "2025-02-01", "revenue": 200.0},
        # 2025-03 ausente a propósito
        {"date": "2026-03-01", "revenue": 999.0},
    ]
    s = rf._yoy_series(hist, [], rf._reader("revenue"))
    assert s["y"][s["x"].index("2026-03-01")] is None


def test_yoy_forecast_segment_sourced_from_history():
    # El segmento del forecast se sirve de HIST, nunca de las fc rows.
    hist = [{"date": "2025-08-01", "revenue": 777.0}]
    fc = [{"date": "2026-08-01", "revenue": 999999.0}]  # valor trampa en fc
    s = rf._yoy_series(hist, fc, rf._reader("revenue"))
    idx = s["x"].index("2026-08-01")
    assert s["y"][idx] == 777.0   # de hist 2025-08, NO 999999 del fc


# ─────────────────────────────────────────────────────────────────────────────
# _METRICS
# ─────────────────────────────────────────────────────────────────────────────

def test_metrics_catalog_has_10_entries():
    assert len(rf._METRICS) == 10


def test_metrics_colors_match_html():
    expected = {
        "revenue": "#FF3300",
        "units": "#E85B03",
        "sessions": "#FBBF24",
        "cvr": "#34D399",
        "aov": "#60A5FA",
        "spend": "#A78BFA",
        "ventasPPC": "#F472B6",
        "acos": "#F87171",
        "tacos": "#22D3EE",
        "salesVelocity": "#FB923C",
    }
    for mid, hexc in expected.items():
        assert rf._METRICS[mid]["color"] == hexc

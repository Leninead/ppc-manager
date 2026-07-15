"""M31 G2 — Tests de _metric_chart (Plotly go.Figure), sin Streamlit.

Inspeccionan `fig.data` (traces) y `fig.layout` (ejes), NO pixels. 100% puros:
Plotly sin runtime de Streamlit, cero fixtures reales.

Invariantes load-bearing:
  - El bridge de G1 LLEGA a la figura (trace de forecast arranca en el último x
    histórico) → `test_forecast_trace_x_starts_at_last_hist_x`.
  - Sin histórico → figura vacía (0 traces), NO excepción (fiel al HTML).
  - forecast dashed, YoY dotted + color washed-out (`+"88"`).
"""

from __future__ import annotations

import pytest

from modules.pages import revenue_forecast as rf


def _hist(date, **kw):
    base = {"date": date, "revenue": 0.0, "units": 0.0, "sessions": 0.0, "cvr": 0.0}
    base.update(kw)
    return base


def _fc(date, **kw):
    base = {"date": date, "revenue": 0.0, "units": 0.0, "sessions": 0.0,
            "cvr": 0.0, "aov": 0.0}
    base.update(kw)
    return base


def _sample_hist():
    return [
        _hist("2026-05-01", revenue=1000.0, units=50.0, sessions=500.0, cvr=10.0),
        _hist("2026-06-01", revenue=1100.0, units=55.0, sessions=520.0, cvr=10.6),
    ]


def _sample_fc():
    return [
        _fc("2026-07-01", revenue=1200.0, units=60.0, sessions=540.0, cvr=11.1),
        _fc("2026-08-01", revenue=1300.0, units=65.0, sessions=560.0, cvr=11.6),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Cantidad de traces
# ─────────────────────────────────────────────────────────────────────────────

def test_metric_chart_has_two_traces_without_yoy():
    fig = rf._metric_chart("revenue", _sample_hist(), _sample_fc(), show_yoy=False)
    assert len(fig.data) == 2   # hist + forecast


def test_metric_chart_has_three_traces_with_yoy():
    fig = rf._metric_chart("revenue", _sample_hist(), _sample_fc(), show_yoy=True)
    assert len(fig.data) == 3   # hist + forecast + yoy


def test_metric_chart_one_trace_when_no_forecast():
    fig = rf._metric_chart("revenue", _sample_hist(), [], show_yoy=False)
    assert len(fig.data) == 1   # solo hist


def test_metric_chart_empty_history_returns_empty_figure():
    fig = rf._metric_chart("revenue", [], _sample_fc(), show_yoy=True)
    assert len(fig.data) == 0   # 0 traces, sin excepción


# ─────────────────────────────────────────────────────────────────────────────
# Estilos de trace
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_trace_is_dashed():
    fig = rf._metric_chart("revenue", _sample_hist(), _sample_fc())
    fc_trace = fig.data[1]
    assert fc_trace.line.dash == "dash"


def test_yoy_trace_is_dotted_and_washed_out():
    hist = [
        _hist("2025-06-01", revenue=900.0),
        _hist("2026-05-01", revenue=1000.0),
        _hist("2026-06-01", revenue=1100.0),
    ]
    fig = rf._metric_chart("revenue", hist, _sample_fc(), show_yoy=True)
    yoy_trace = fig.data[2]
    assert yoy_trace.line.dash == "dot"
    # Plotly rechaza hex de 8 dígitos → el alpha 0x88 del HTML se porta a rgba.
    # 0x88 = 136/255 ≈ 0.533. Sigue siendo washed-out y trazable a "88".
    assert yoy_trace.line.color.startswith("rgba(")
    assert yoy_trace.line.color.endswith("0.533)")
    assert yoy_trace.line.color != rf._METRICS["revenue"]["color"]  # distinto del sólido


def test_forecast_trace_x_starts_at_last_hist_x():
    # El bridge de G1 llega a la figura: el forecast arranca en el último x hist.
    hist = _sample_hist()
    fc = _sample_fc()
    fig = rf._metric_chart("revenue", hist, fc)
    hist_trace, fc_trace = fig.data[0], fig.data[1]
    assert fc_trace.x[0] == hist_trace.x[-1] == "2026-06-01"
    assert fc_trace.y[0] == hist_trace.y[-1] == 1100.0


def test_connectgaps_true_on_all_traces():
    hist = [
        _hist("2025-06-01", revenue=900.0),
        _hist("2026-05-01", revenue=1000.0),
        _hist("2026-06-01", revenue=1100.0),
    ]
    fig = rf._metric_chart("revenue", hist, _sample_fc(), show_yoy=True)
    assert len(fig.data) == 3
    for trace in fig.data:
        assert trace.connectgaps is True


# ─────────────────────────────────────────────────────────────────────────────
# Ejes según unidad
# ─────────────────────────────────────────────────────────────────────────────

def test_currency_axis_has_dollar_prefix():
    fig = rf._metric_chart("revenue", _sample_hist(), _sample_fc())
    assert fig.layout.yaxis.tickprefix == "$"


def test_percent_axis_has_pct_suffix():
    fig = rf._metric_chart("cvr", _sample_hist(), _sample_fc())
    assert fig.layout.yaxis.ticksuffix == "%"


# ─────────────────────────────────────────────────────────────────────────────
# Los 4 charts del patrón construyen
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("metric_id", ["revenue", "sessions", "cvr", "units"])
def test_all_four_pattern_metrics_build(metric_id):
    fig = rf._metric_chart(metric_id, _sample_hist(), _sample_fc(), show_yoy=True)
    assert fig is not None
    assert len(fig.data) == 3   # hist + fc + yoy (aunque yoy sea todo None, el trace existe)

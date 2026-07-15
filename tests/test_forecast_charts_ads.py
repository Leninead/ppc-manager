"""M31 G3 — Tests de _ads_chart y _acos_tacos_chart (Plotly go.Figure), sin Streamlit.

Los 2 charts multi-métrica: meten DOS métricas del catálogo en la MISMA figura
(hasta 5 traces). Inspeccionan `fig.data` (traces) y `fig.layout` (ejes), NO
pixels. 100% puros: Plotly sin runtime de Streamlit, cero fixtures reales.
Mismo estilo que `tests/test_forecast_charts_figures.py` (G2).

Invariantes load-bearing:
  - _ads_chart: UN solo YoY (el de SPEND), y `rangemode="tozero"` en Y — único de
    los 7 charts con beginAtZero.
  - _acos_tacos_chart: dashed = FORECAST (no TACOS). Desviación consciente del
    HTML — si alguien "vuelve al HTML" y hace TACOS dashed, el test lo frena.
  - _acos_tacos_chart: el forecast LEE `f["acos"]` (override del AM), no recalcula
    spend/ventasPPC*100 (anti-bug F6.3c: chart == tabla).
"""

from __future__ import annotations

from modules.pages import revenue_forecast as rf


def _hist(date, **kw):
    base = {"date": date, "revenue": 0.0, "units": 0.0, "sessions": 0.0,
            "cvr": 0.0, "spend": 0.0, "ventasPPC": 0.0}
    base.update(kw)
    return base


def _fc(date, **kw):
    base = {"date": date, "revenue": 0.0, "units": 0.0, "sessions": 0.0,
            "cvr": 0.0, "aov": 0.0, "spend": 0.0, "ventasPPC": 0.0,
            "acos": 0.0, "tacos": 0.0}
    base.update(kw)
    return base


def _sample_hist():
    return [
        _hist("2026-05-01", revenue=1000.0, spend=200.0, ventasPPC=800.0),
        _hist("2026-06-01", revenue=1100.0, spend=220.0, ventasPPC=880.0),
    ]


def _sample_fc():
    return [
        _fc("2026-07-01", revenue=1200.0, spend=240.0, ventasPPC=960.0,
            acos=25.0, tacos=20.0),
        _fc("2026-08-01", revenue=1300.0, spend=260.0, ventasPPC=1040.0,
            acos=25.0, tacos=20.0),
    ]


def _by_name(fig, name):
    """Devuelve el primer trace cuyo `name` coincide exacto, o None."""
    for tr in fig.data:
        if tr.name == name:
            return tr
    return None


# ═════════════════════════════════════════════════════════════════════════════
# _ads_chart
# ═════════════════════════════════════════════════════════════════════════════

def test_ads_chart_has_four_traces_without_yoy():
    fig = rf._ads_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    assert len(fig.data) == 4   # spend hist/fc + vppc hist/fc


def test_ads_chart_has_five_traces_with_yoy():
    fig = rf._ads_chart(_sample_hist(), _sample_fc(), show_yoy=True)
    assert len(fig.data) == 5   # + 1 solo YoY


def test_ads_chart_yoy_is_spend_only():
    # LOAD-BEARING: con 5 líneas, un 2do YoY vuelve el chart ilegible. Exactamente
    # un trace YoY, y es el de Spend (nunca Ventas PPC).
    fig = rf._ads_chart(_sample_hist(), _sample_fc(), show_yoy=True)
    yoy = [tr for tr in fig.data if "YoY" in (tr.name or "")]
    assert len(yoy) == 1
    assert "Spend" in yoy[0].name
    assert "Ventas PPC" not in yoy[0].name


def test_ads_chart_rangemode_tozero():
    # LOAD-BEARING: único de los 7 charts con beginAtZero (HTML L2653).
    fig = rf._ads_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    assert fig.layout.yaxis.rangemode == "tozero"


def test_ads_chart_forecast_traces_are_dashed():
    fig = rf._ads_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    sp_fc = _by_name(fig, "Spend (forecast)")
    vp_fc = _by_name(fig, "Ventas PPC (forecast)")
    assert sp_fc is not None and vp_fc is not None
    assert sp_fc.line.dash == "dash"
    assert vp_fc.line.dash == "dash"


def test_ads_chart_spend_and_vppc_have_different_colors():
    fig = rf._ads_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    sp_hist = _by_name(fig, "Spend (hist.)")
    vp_hist = _by_name(fig, "Ventas PPC (hist.)")
    assert sp_hist is not None and vp_hist is not None
    assert sp_hist.line.color != vp_hist.line.color


def test_ads_chart_empty_history_returns_empty_figure():
    fig = rf._ads_chart([], _sample_fc(), show_yoy=True)
    assert len(fig.data) == 0   # 0 traces, sin excepción


def test_ads_chart_handles_none_and_empty_spend():
    # Filas hist con spend AUSENTE (None) y VACÍO ("") → _safe_num → None (hueco),
    # no excepción. Se ejercita también el path YoY.
    hist = [
        _hist("2026-05-01", spend=None, ventasPPC=800.0),
        _hist("2026-06-01", spend="", ventasPPC=880.0),
    ]
    fig = rf._ads_chart(hist, _sample_fc(), show_yoy=True)
    assert len(fig.data) == 5   # construyó sin romper


# ═════════════════════════════════════════════════════════════════════════════
# _acos_tacos_chart
# ═════════════════════════════════════════════════════════════════════════════

def test_acos_chart_has_four_traces_without_yoy():
    fig = rf._acos_tacos_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    assert len(fig.data) == 4   # acos hist/fc + tacos hist/fc


def test_acos_chart_has_five_traces_with_yoy():
    fig = rf._acos_tacos_chart(_sample_hist(), _sample_fc(), show_yoy=True)
    assert len(fig.data) == 5   # + 1 solo YoY


def test_acos_chart_yoy_is_acos_only():
    # LOAD-BEARING: un solo YoY, el de ACOS (nunca TACOS).
    fig = rf._acos_tacos_chart(_sample_hist(), _sample_fc(), show_yoy=True)
    yoy = [tr for tr in fig.data if "YoY" in (tr.name or "")]
    assert len(yoy) == 1
    assert "ACOS" in yoy[0].name
    assert "TACOS" not in yoy[0].name


def test_acos_chart_forecast_dashed_not_tacos():
    # EL MÁS IMPORTANTE: afirma la desviación consciente del HTML. dashed = FORECAST
    # en los 7 charts. El trace de TACOS HISTÓRICO es SÓLIDO (dash != "dash"); los
    # dashed son los de forecast. Si alguien "vuelve al HTML" y hace TACOS dashed
    # para distinguirlo de ACOS, este test lo frena.
    fig = rf._acos_tacos_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    tacos_hist = _by_name(fig, "TACOS %")
    assert tacos_hist is not None
    assert tacos_hist.line.dash != "dash"          # histórico SÓLIDO
    assert _by_name(fig, "ACOS % (forecast)").line.dash == "dash"
    assert _by_name(fig, "TACOS % (forecast)").line.dash == "dash"


def test_acos_chart_forecast_values_read_not_computed():
    # LOAD-BEARING (anti-F6.3c): el forecast LEE f["acos"], NO recalcula
    # spend/ventasPPC*100. Acá spend/vppc darían 30.0, pero acos=15.0 (override del
    # AM). El trace de forecast debe traer 15.0 → gana el override.
    # Ojo BRIDGE: y[0] es el último punto HISTÓRICO; el 15.0 está en y[1].
    fc = [_fc("2026-07-01", acos=15.0, spend=300.0, ventasPPC=1000.0)]
    fig = rf._acos_tacos_chart(_sample_hist(), fc, show_yoy=False)
    ac_fc = _by_name(fig, "ACOS % (forecast)")
    assert ac_fc is not None
    assert ac_fc.y[1] == 15.0


def test_acos_chart_percent_axis_suffix():
    fig = rf._acos_tacos_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    assert fig.layout.yaxis.ticksuffix == "%"


def test_acos_chart_no_rangemode():
    # `rangemode="tozero"` es exclusivo de Ads — acá NO va.
    fig = rf._acos_tacos_chart(_sample_hist(), _sample_fc(), show_yoy=False)
    assert fig.layout.yaxis.rangemode != "tozero"


def test_acos_chart_empty_history_returns_empty_figure():
    fig = rf._acos_tacos_chart([], _sample_fc(), show_yoy=True)
    assert len(fig.data) == 0   # 0 traces, sin excepción

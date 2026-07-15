"""M31 G4 — Tests de _axis_split y _custom_chart (Plotly go.Figure), sin Streamlit.

_custom_chart mete N métricas del catálogo en 1 figura con hasta 2 ejes Y. Capa
PURA: `metric_ids` es argumento (los chips/session_state son de G5). Inspeccionan
`fig.data` y `fig.layout`, NO pixels. Mismo estilo que test_forecast_charts_ads.py.

Invariantes load-bearing:
  - _axis_split: percent SIEMPRE a la derecha, sin importar el orden en metric_ids.
  - _axis_split: currency+count sin percent → orden de APARICIÓN (no alfabético).
  - CASO BORDE (3 unidades): count comparte eje derecho con percent — NO hay 3er
    eje. Comportamiento que Edu ya vio; portado verbatim, documentado en test.
  - _custom_chart: los 3 traces (hist/fc/yoy) de una métrica van al MISMO eje.
  - dashed=forecast, dotted=yoy, sin rangemode (eso es de _ads_chart).
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
        _hist("2026-05-01", revenue=1000.0, units=50.0, spend=200.0, ventasPPC=800.0),
        _hist("2026-06-01", revenue=1100.0, units=55.0, spend=220.0, ventasPPC=880.0),
    ]


def _sample_fc():
    return [
        _fc("2026-07-01", revenue=1200.0, units=60.0, spend=240.0,
            ventasPPC=960.0, acos=25.0, tacos=20.0),
        _fc("2026-08-01", revenue=1300.0, units=65.0, spend=260.0,
            ventasPPC=1040.0, acos=25.0, tacos=20.0),
    ]


def _names_axis(fig, needle):
    """[(name, yaxis)] de los traces cuyo name contiene `needle`."""
    return [(t.name, t.yaxis) for t in fig.data if needle in (t.name or "")]


# ═════════════════════════════════════════════════════════════════════════════
# _axis_split — la regla del doble eje, aislada
# ═════════════════════════════════════════════════════════════════════════════

def test_axis_split_single_unit():
    # revenue y spend son ambas currency → una sola unidad, sin eje derecho.
    assert rf._axis_split(["revenue", "spend"]) == ("currency", None)


def test_axis_split_percent_goes_right():
    assert rf._axis_split(["revenue", "acos"]) == ("currency", "percent")


def test_axis_split_percent_right_even_if_listed_first():
    # LOAD-BEARING: percent SIEMPRE a la derecha, sin importar el orden.
    assert rf._axis_split(["acos", "revenue"]) == ("currency", "percent")


def test_axis_split_currency_and_count_uses_appearance_order():
    # units (count) aparece primero → es left. NO alfabético.
    assert rf._axis_split(["units", "revenue"]) == ("count", "currency")


def test_axis_split_three_units_percent_still_right():
    # CASO BORDE: currency+count+percent → left=currency, right=percent.
    # count NO tiene eje propio (documentado como intencional).
    assert rf._axis_split(["revenue", "units", "acos"]) == ("currency", "percent")


# ═════════════════════════════════════════════════════════════════════════════
# _custom_chart
# ═════════════════════════════════════════════════════════════════════════════

def test_custom_chart_empty_history_returns_empty_figure():
    fig = rf._custom_chart(["revenue"], [], _sample_fc(), show_yoy=True)
    assert len(fig.data) == 0   # 0 traces, sin excepción


def test_custom_chart_empty_metric_ids_returns_empty_figure():
    fig = rf._custom_chart([], _sample_hist(), _sample_fc(), show_yoy=True)
    assert len(fig.data) == 0   # 0 traces, sin excepción


def test_custom_chart_unknown_metric_id_is_ignored():
    fig = rf._custom_chart(["revenue", "noexiste"], _sample_hist(), _sample_fc())
    # Sólo traces de revenue (hist + fc); "noexiste" ignorado, sin romper.
    assert len(fig.data) == 2
    assert all("Revenue" in (t.name or "") for t in fig.data)


def test_custom_chart_traces_per_metric_without_yoy():
    fig = rf._custom_chart(["revenue"], _sample_hist(), _sample_fc(), show_yoy=False)
    assert len(fig.data) == 2   # hist + fc


def test_custom_chart_traces_per_metric_with_yoy():
    fig = rf._custom_chart(["revenue"], _sample_hist(), _sample_fc(), show_yoy=True)
    assert len(fig.data) == 3   # hist + fc + yoy


def test_custom_chart_two_metrics_with_yoy_has_six_traces():
    fig = rf._custom_chart(["revenue", "acos"], _sample_hist(), _sample_fc(),
                           show_yoy=True)
    assert len(fig.data) == 6   # 3 por métrica


def test_custom_chart_percent_metric_on_right_axis():
    # LOAD-BEARING: revenue (currency) en el eje izquierdo, acos (percent) en y2.
    fig = rf._custom_chart(["revenue", "acos"], _sample_hist(), _sample_fc())
    for name, ax in _names_axis(fig, "Revenue"):
        assert ax in ("y", None)     # izquierdo (default)
    for name, ax in _names_axis(fig, "ACOS"):
        assert ax == "y2"


def test_custom_chart_all_traces_of_a_metric_share_axis():
    # LOAD-BEARING: los 3 traces de acos (hist/fc/yoy) van todos a "y2".
    fig = rf._custom_chart(["revenue", "acos"], _sample_hist(), _sample_fc(),
                           show_yoy=True)
    acos_axes = [ax for _, ax in _names_axis(fig, "ACOS")]
    assert len(acos_axes) == 3
    assert set(acos_axes) == {"y2"}


def test_custom_chart_single_unit_has_no_second_axis():
    # revenue + spend (ambas currency) → NO se configura yaxis2.
    fig = rf._custom_chart(["revenue", "spend"], _sample_hist(), _sample_fc())
    assert "yaxis2" not in fig.layout.to_plotly_json()


def test_custom_chart_right_axis_has_no_grid():
    # Verbatim del HTML: eje secundario sin grilla (no duplica la del izquierdo).
    fig = rf._custom_chart(["revenue", "acos"], _sample_hist(), _sample_fc())
    assert fig.layout.yaxis2.showgrid is False


def test_custom_chart_third_unit_shares_right_axis():
    # CASO BORDE documentado como INTENCIONAL: units (count) cae en "y2" junto al
    # percent — con 2 ejes no hay salida limpia. NO es un bug.
    fig = rf._custom_chart(["revenue", "units", "acos"], _sample_hist(), _sample_fc())
    for name, ax in _names_axis(fig, "Units"):
        assert ax == "y2"


def test_custom_chart_forecast_dashed_yoy_dotted():
    # Coherencia con los otros 6 charts.
    fig = rf._custom_chart(["revenue"], _sample_hist(), _sample_fc(), show_yoy=True)
    by = {t.name: t for t in fig.data}
    assert by["Revenue (forecast)"].line.dash == "dash"
    assert by["Revenue YoY"].line.dash == "dot"


def test_custom_chart_no_rangemode():
    # rangemode="tozero" es exclusivo de _ads_chart.
    fig = rf._custom_chart(["revenue", "acos"], _sample_hist(), _sample_fc())
    assert fig.layout.yaxis.rangemode != "tozero"

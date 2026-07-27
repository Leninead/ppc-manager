"""M31 F7-A2 — la línea `actual` (verde) en los 7 charts.

A1 dejó `_actual_series(hist, actual, accessor) -> {x, y, partial}`. A2 sólo la
DIBUJA: cero lógica de series nueva.

Decisiones visuales (Lenin):
    - Línea `actual` = verde `#22C55E`, SÓLIDA. Más saturado que el CVR
      `#34D399` del catálogo para no confundirse cuando el chart de CVR tenga
      las dos.
    - Punto de un mes PARCIAL (`partial is True`) = marcador HUECO
      (`circle-open`). Sólo cambia el SÍMBOLO: ni dash (es del forecast) ni
      otro color.

Contrato aditivo: los 4 builders suman `actual_rows=None` al final de su firma.
Con `None` o `[]` la figura es EXACTAMENTE la de hoy — los ~60 tests de G2-G4
pasan sin tocarse.

Nota Plotly 6.7.0 (verificado, no asumido):
    - `marker.symbol` acepta un array y lo normaliza a TUPLA (no lista).
    - El default de `marker.symbol` es `None` (no `"circle"`). `None` renderiza
      el círculo lleno. Por eso los roles viejos y el `actual` sin `partial`
      dejan el símbolo SIN setear: es lo que garantiza cero cambio.
"""

from __future__ import annotations

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Datos mínimos
# ─────────────────────────────────────────────────────────────────────────────

def _hist():
    return [
        {"date": "2026-05-01", "revenue": 100.0, "units": 10, "sessions": 100,
         "cvr": 10.0, "spend": 30.0, "ventasPPC": 60.0},
        {"date": "2026-06-01", "revenue": 200.0, "units": 20, "sessions": 200,
         "cvr": 10.0, "spend": 40.0, "ventasPPC": 80.0},
    ]


def _fc():
    return [
        {"date": "2026-07-01", "revenue": 250.0, "units": 25, "sessions": 250,
         "cvr": 10.0, "spend": 50.0, "ventasPPC": 100.0, "aov": 10.0,
         "acos": 50.0, "tacos": 20.0, "salesVelocity": 0.8},
    ]


def _actual():
    """Julio cerrado + agosto corriendo (parcial)."""
    return [
        {"date": "2026-07-01", "revenue": 230.0, "units": 23, "sessions": 240,
         "cvr": 9.6, "spend": 55.0, "ventasPPC": 90.0, "partial": False},
        {"date": "2026-08-01", "revenue": 80.0, "units": 8, "sessions": 90,
         "cvr": 8.9, "spend": 20.0, "ventasPPC": 30.0, "partial": True},
    ]


def _green_traces(fig):
    return [t for t in fig.data if t.line.color == rf._CHART_ACTUAL]


# ─────────────────────────────────────────────────────────────────────────────
# _chart_trace — role "actual" + param aditivo `partial`
# ─────────────────────────────────────────────────────────────────────────────

def test_chart_trace_role_actual_es_solido_y_del_color_pasado():
    """Dato real cerrado → mismo peso visual que la línea histórica: sólida,
    width 2. El dash queda reservado al forecast.
    """
    tr = rf._chart_trace([1, 2], [3, 4], "Revenue (real)", rf._CHART_ACTUAL, "actual")
    assert tr.line.color == rf._CHART_ACTUAL
    assert tr.line.dash is None          # SÓLIDA
    assert tr.line.width == 2
    assert tr.line.shape == "spline"
    assert tr.connectgaps is True


def test_chart_trace_actual_sin_partial_no_setea_symbol():
    """Sin `partial`, el símbolo queda en el default de Plotly (None = círculo
    lleno). NO un array. Es lo que garantiza que los roles viejos no cambien.
    """
    tr = rf._chart_trace([1, 2], [3, 4], "x", rf._CHART_ACTUAL, "actual")
    assert tr.marker.symbol is None
    assert not isinstance(tr.marker.symbol, (list, tuple))


def test_chart_trace_partial_produce_array_de_simbolos():
    """`partial=[False, True]` → hueco SÓLO en el punto parcial.

    Plotly 6.7.0 normaliza el array a TUPLA (verificado contra la lib, no asumido).
    """
    tr = rf._chart_trace([1, 2], [3, 4], "x", rf._CHART_ACTUAL, "actual",
                         partial=[False, True])
    assert tuple(tr.marker.symbol) == ("circle", "circle-open")


def test_chart_trace_partial_none_cuenta_como_lleno():
    """`partial=None` en un punto = cobertura DESCONOCIDA (BR mensual, ver A1).
    No se pinta como parcial: sólo `True` abre el marcador.
    """
    tr = rf._chart_trace([1, 2, 3], [1, 2, 3], "x", rf._CHART_ACTUAL, "actual",
                         partial=[None, False, True])
    assert tuple(tr.marker.symbol) == ("circle", "circle", "circle-open")


def test_chart_trace_roles_viejos_no_cambian():
    """🔴 Guard: `partial` es ADITIVO. hist/fc/yoy no lo pasan y su símbolo sigue
    sin setear (los tests de G3 pasan sin tocarse).
    """
    for role, dash in (("hist", None), ("fc", "dash"), ("yoy", "dot")):
        tr = rf._chart_trace([1, 2], [3, 4], "x", "#FF3300", role)
        assert tr.marker.symbol is None, f"role {role}"
        assert tr.line.dash == dash, f"role {role}"


def test_chart_trace_partial_aplica_a_cualquier_role():
    """El param no está acoplado al role: si se pasa, se aplica. Mantiene
    `_chart_trace` como una sola función de estilo, sin ramas especiales.
    """
    tr = rf._chart_trace([1, 2], [3, 4], "x", "#FF3300", "hist", partial=[True, False])
    assert tuple(tr.marker.symbol) == ("circle-open", "circle")


# ─────────────────────────────────────────────────────────────────────────────
# _metric_chart
# ─────────────────────────────────────────────────────────────────────────────

def test_metric_chart_sin_actual_no_dibuja_verde():
    """🔴 No-regresión: hist + fc + yoy = 3 traces, ninguno verde."""
    fig = rf._metric_chart("revenue", _hist(), _fc(), True)
    assert len(fig.data) == 3
    assert _green_traces(fig) == []


def test_metric_chart_actual_none_y_lista_vacia_son_equivalentes():
    """`None` y `[]` dan la MISMA figura que el llamado sin el param."""
    base = rf._metric_chart("revenue", _hist(), _fc(), True)
    con_none = rf._metric_chart("revenue", _hist(), _fc(), True, actual_rows=None)
    con_vacia = rf._metric_chart("revenue", _hist(), _fc(), True, actual_rows=[])
    assert len(con_none.data) == len(base.data) == len(con_vacia.data)
    assert _green_traces(con_none) == [] and _green_traces(con_vacia) == []


def test_metric_chart_con_actual_suma_un_trace():
    fig = rf._metric_chart("revenue", _hist(), _fc(), True, actual_rows=_actual())
    assert len(fig.data) == 4
    verdes = _green_traces(fig)
    assert len(verdes) == 1
    assert verdes[0].name == "Revenue (real)"


def test_metric_chart_actual_arranca_en_el_bridge():
    """La línea real sale del MISMO punto que la de forecast: el último
    histórico. Así se ve dónde divergen real y proyectado.
    """
    hist = _hist()
    fig = rf._metric_chart("revenue", hist, _fc(), False, actual_rows=_actual())
    verde = _green_traces(fig)[0]
    assert verde.x[0] == hist[-1]["date"]          # "2026-06-01"
    assert verde.y[0] == hist[-1]["revenue"]       # 200.0
    assert list(verde.x) == ["2026-06-01", "2026-07-01", "2026-08-01"]


def test_metric_chart_marca_hueco_solo_el_mes_parcial():
    """Bridge (histórico) y julio (cerrado) llenos; agosto (corriendo) hueco."""
    fig = rf._metric_chart("revenue", _hist(), _fc(), False, actual_rows=_actual())
    verde = _green_traces(fig)[0]
    assert tuple(verde.marker.symbol) == ("circle", "circle", "circle-open")


def test_metric_chart_sin_historico_sigue_devolviendo_figura_vacia():
    """El guard de hist vacío manda sobre `actual` (fiel al HTML)."""
    fig = rf._metric_chart("revenue", [], _fc(), True, actual_rows=_actual())
    assert len(fig.data) == 0


# ─────────────────────────────────────────────────────────────────────────────
# _ads_chart / _acos_tacos_chart
# ─────────────────────────────────────────────────────────────────────────────

def test_ads_chart_sin_actual_no_cambia():
    """🔴 No-regresión: spend hist/fc + vppc hist/fc + 1 YoY = 5 traces."""
    fig = rf._ads_chart(_hist(), _fc(), True)
    assert len(fig.data) == 5
    assert _green_traces(fig) == []


def test_ads_chart_con_actual_dibuja_spend_y_ventas_ppc():
    """DECISIÓN: las DOS métricas llevan línea real, igual que el forecast dibuja
    las dos. Se distinguen por legend + hover unificado.
    """
    fig = rf._ads_chart(_hist(), _fc(), True, actual_rows=_actual())
    assert len(fig.data) == 7
    nombres = [t.name for t in _green_traces(fig)]
    assert nombres == ["Spend (real)", "Ventas PPC (real)"]


def test_acos_tacos_chart_sin_actual_no_cambia():
    fig = rf._acos_tacos_chart(_hist(), _fc(), True)
    assert len(fig.data) == 5
    assert _green_traces(fig) == []


def test_acos_tacos_chart_con_actual_dibuja_ambas():
    fig = rf._acos_tacos_chart(_hist(), _fc(), True, actual_rows=_actual())
    assert len(fig.data) == 7
    nombres = [t.name for t in _green_traces(fig)]
    assert nombres == ["ACOS % (real)", "TACOS % (real)"]


def test_acos_actual_se_calcula_desde_el_real_no_desde_el_forecast():
    """ACOS real = spend/ventasPPC*100 de las filas de `actual` (accessor
    `from_hist`), NUNCA los targets que el motor escribió en el forecast.
    """
    fig = rf._acos_tacos_chart(_hist(), _fc(), False, actual_rows=_actual())
    verde = _green_traces(fig)[0]
    assert verde.name == "ACOS % (real)"
    # julio real: 55/90*100 ; agosto real: 20/30*100
    assert verde.y[1] == 55.0 / 90.0 * 100.0
    assert verde.y[2] == 20.0 / 30.0 * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# _custom_chart
# ─────────────────────────────────────────────────────────────────────────────

def test_custom_chart_sin_actual_no_cambia():
    """🔴 No-regresión: 2 métricas × (hist + fc + yoy) = 6 traces."""
    fig = rf._custom_chart(["revenue", "cvr"], _hist(), _fc(), True)
    assert len(fig.data) == 6
    assert _green_traces(fig) == []


def test_custom_chart_con_actual_suma_uno_por_metrica():
    fig = rf._custom_chart(["revenue", "cvr"], _hist(), _fc(), True,
                           actual_rows=_actual())
    assert len(fig.data) == 8
    nombres = [t.name for t in _green_traces(fig)]
    assert nombres == ["Revenue (real)", "CVR % (real)"]


def test_custom_chart_actual_va_al_eje_de_su_metrica():
    """revenue (currency) → eje izquierdo; cvr (percent) → eje derecho. La línea
    real tiene que ir al MISMO eje que su métrica, o la escala miente.
    """
    fig = rf._custom_chart(["revenue", "cvr"], _hist(), _fc(), False,
                           actual_rows=_actual())
    por_nombre = {t.name: t for t in fig.data}
    assert por_nombre["Revenue (real)"].yaxis == por_nombre["Revenue"].yaxis == "y"
    assert por_nombre["CVR % (real)"].yaxis == por_nombre["CVR %"].yaxis == "y2"


def test_custom_chart_metric_id_desconocido_se_sigue_ignorando():
    """Guard existente intacto con `actual_rows` presente."""
    fig = rf._custom_chart(["revenue", "no-existe"], _hist(), _fc(), False,
                           actual_rows=_actual())
    assert len(_green_traces(fig)) == 1

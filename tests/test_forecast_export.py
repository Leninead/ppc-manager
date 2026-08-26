"""M31 · G6 — Tests del export HTML self-contained.

Puros: operan sobre el string HTML devuelto por la capa pura. Sin runtime de
Streamlit, sin session_state, sin browser.

`_build_export_html` recibe `show_yoy` como parámetro (default True) justamente
para que estos tests NO dependan del buffer de G5 en session_state.
"""

from datetime import date

import pytest

from modules.pages.revenue_forecast import (
    _CHART_ACTUAL,
    _CHART_ACTUAL_WASHED,
    _acos_tacos_chart,
    _ads_chart,
    _asin_table_html,
    _build_export_html,
    _cliente_slug,
    _custom_chart,
    _forecast_table_html,
    _metric_chart,
)


def _hist(n: int = 14) -> list:
    """Histórico sintético: n meses consecutivos desde 2025-01."""
    out = []
    for i in range(n):
        y, m = 2025 + i // 12, i % 12 + 1
        out.append({
            "date": f"{y}-{m:02d}-01",
            "revenue": 10000.0 + i * 500,
            "units": 200.0 + i * 5,
            "sessions": 4000.0 + i * 50,
            "cvr": 5.0,
            "spend": 1500.0,
            "ventasPPC": 4000.0,
        })
    return out


def _fc(n: int = 3) -> list:
    """Forecast sintético: n meses proyectados."""
    return [
        {
            "date": f"2026-{m:02d}-01",
            "revenue": 20000.0 + m,
            "aov": 50.0,
            "units": 400.0,
            "salesVelocity": 13.0,
            "sessions": 6000.0,
            "cvr": 6.5,
            "spend": 2000.0,
            "ventasPPC": 7000.0,
            "acos": 28.5,
            "tacos": 10.0,
            "pctVtasPPC": 35.0,
        }
        for m in range(1, n + 1)
    ]


def _cur(**over) -> dict:
    base = {
        "id": "c1",
        "name": "Dermaglos",
        "currency": "USD",
        "historical": _hist(),
        "forecast": _fc(),
    }
    base.update(over)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# _cliente_slug — filename filesystem-safe (helper preexistente, reusado por G6)
# ─────────────────────────────────────────────────────────────────────────────

def test_safe_filename_strips_special_chars():
    assert _cliente_slug("Dermaglos (US)!") == "dermaglos_us"


def test_safe_filename_spaces_to_underscore():
    assert _cliente_slug("Love To Dream MX") == "love_to_dream_mx"


def test_safe_filename_empty_falls_back():
    assert _cliente_slug("") == "cuenta"


# ─────────────────────────────────────────────────────────────────────────────
# _forecast_table_html
# ─────────────────────────────────────────────────────────────────────────────

def test_table_has_row_per_forecast_month():
    html = _forecast_table_html(_fc(3))
    assert html.count("<tr>") == 4          # 1 header + 3 meses
    assert html.count("</tbody>") == 1


def test_table_none_renders_as_dash():
    rows = _fc(1)
    rows[0]["spend"] = None
    rows[0]["acos"] = None
    rows[0]["units"] = ""                   # '' rompía los _fmt_* sin _table_cell
    html = _forecast_table_html(rows)
    assert "None" not in html
    assert "<td>—</td>" in html


def test_table_formats_currency_and_percent():
    html = _forecast_table_html(_fc(1))
    assert "$20,001" in html                # revenue 20001.0 → currency 0 dec
    assert "28.5%" in html                  # acos → percent 1 dec


def test_table_respects_account_currency():
    """La tabla NO hardcodea '$': usa el símbolo de la moneda de la cuenta.

    Se usa EUR (y no MXN) porque `_CURRENCY_SYMBOLS` mapea MXN → '$' — port
    fiel del HTML original, donde MXN y USD comparten símbolo. Con MXN este
    test no probaría nada.
    """
    html = _forecast_table_html(_fc(1), currency="EUR")
    assert "€20,001" in html
    assert "$" not in html


def test_table_empty_forecast_returns_empty_string():
    assert _forecast_table_html([]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# _build_export_html
# ─────────────────────────────────────────────────────────────────────────────

def test_export_is_valid_html_document():
    html = _build_export_html(_cur())
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert '<meta charset="UTF-8">' in html


def test_export_includes_client_name():
    assert "Dermaglos" in _build_export_html(_cur())


def test_export_embeds_seven_charts():
    """Plotly genera un div .plotly-graph-div por figura → deben ser 7."""
    html = _build_export_html(_cur())
    assert html.count("plotly-graph-div") == 7


def test_export_loads_plotlyjs_once():
    """🔴 LOAD-BEARING (tamaño). Sólo la 1ra figura carga plotly.js desde el CDN.

    Marcador REAL verificado contra plotly 6.7.0: el src es
    `https://cdn.plot.ly/plotly-3.5.0.min.js` → el substring estable es
    `cdn.plot.ly` (`plotly.min.js` NO aparece nunca: el archivo lleva la
    versión en el nombre).

    Si esto da 7, alguien puso include_plotlyjs=True/"cdn" en las 7 figuras y el
    reporte pesa ~24MB (Gmail lo rebota).
    """
    html = _build_export_html(_cur())
    assert html.count("cdn.plot.ly") == 1


def test_export_empty_history_no_exception():
    html = _build_export_html(_cur(historical=[], forecast=[]))
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "Sin datos para exportar" in html
    assert "plotly-graph-div" not in html


def test_export_escapes_note():
    html = _build_export_html(_cur(), note="<script>alert('xss')</script>")
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html


def test_export_renders_note_when_present():
    html = _build_export_html(_cur(), note="Proyección conservadora.")
    assert "Proyección conservadora." in html
    assert 'class="note"' in html


def test_export_omits_note_block_when_blank():
    assert 'class="note"' not in _build_export_html(_cur(), note="   ")


def test_export_uses_capybaras_accent():
    html = _build_export_html(_cur())
    assert "#E84000" in html
    assert "<style>" in html


def test_export_includes_summary_and_table():
    html = _build_export_html(_cur())
    assert "Resumen de la proyección" in html
    assert "Detalle del forecast" in html
    assert "2026-01-01" in html          # una fila del forecast


def test_export_escapes_client_name():
    html = _build_export_html(_cur(name="A & B <Co>"))
    assert "A &amp; B &lt;Co&gt;" in html


def test_export_show_yoy_toggle_respected():
    """El reporte RESPETA el toggle del AM: los traces YoY aparecen sólo si on.

    NO se compara `on != off`: Plotly le pone un uuid aleatorio a cada div, así
    que dos builds NUNCA son string-iguales y esa aserción pasaría aunque
    `show_yoy` se ignorara por completo. Se afirma el marcador real: los traces
    YoY se llaman '{label} YoY' (L2476).
    """
    on = _build_export_html(_cur(), show_yoy=True)
    off = _build_export_html(_cur(), show_yoy=False)
    assert "YoY" in on
    assert "YoY" not in off


def test_export_custom_reflects_selection():
    """El 7º chart (Custom) refleja la selección del AM, no ["revenue"] fijo.

    Antes del fix, `_custom_chart` recibía `["revenue"]` hardcodeado → el Custom
    era un DUPLICADO exacto del 1er chart. El trace de ACOS sólo puede venir del
    Custom: ningún otro de los 7 charts nombra 'ACOS %' (el de ACOS/TACOS usa el
    label del catálogo también, así que se compara el CONTEO, no la presencia).
    """
    default = _build_export_html(_cur())                               # → revenue

    # Señal BINARIA: 'Sales Velocity' no aparece en NINGUNO de los otros 6
    # charts, así que su presencia sólo puede venir del Custom.
    sv = _build_export_html(_cur(), custom_metrics=["salesVelocity"])
    assert "Sales Velocity" not in default
    assert "Sales Velocity" in sv

    # El caso pedido (acos). Se compara con '>' y NO con aritmética exacta:
    # cada métrica aporta 3 traces (hist + forecast + YoY) y además 'TACOS %'
    # CONTIENE 'ACOS %' como substring → el delta real es +3, no +1.
    picked = _build_export_html(_cur(), custom_metrics=["acos", "revenue"])
    assert picked.count("ACOS %") > default.count("ACOS %")


def test_export_custom_empty_falls_back_to_revenue():
    """`[]` → default (revenue), NO un chart en blanco.

    G5 enforcea el mínimo de 1 chip, así que en producción no se dispara; el
    guard cubre el caller futuro que pase [] sin saberlo.

    Se comparan CONTEOS, no los strings enteros: los uuid de los divs de Plotly
    hacen que dos builds nunca sean iguales.
    """
    empty = _build_export_html(_cur(), custom_metrics=[])
    default = _build_export_html(_cur())
    assert empty.count("plotly-graph-div") == 7      # el 7º existe, no se cayó
    assert empty.count("ACOS %") == default.count("ACOS %")   # se comporta como revenue


# ─────────────────────────────────────────────────────────────────────────────
# F7-A4 — la línea `actual` (el REAL) en el export
# ─────────────────────────────────────────────────────────────────────────────
#
# Se cuentan marcadores dentro del HTML, nunca se comparan documentos enteros:
# los uuid de los divs de Plotly hacen que dos builds nunca sean iguales (misma
# razón que `test_export_custom_empty_falls_back_to_revenue`).

def _actual(date_str: str = "2026-07-01", partial=True) -> list:
    """UNA fila de la capa `actual`, shape de `historical` + cobertura.

    Posterior al último mes de `_hist()` (2026-02) → siempre hay ancla de bridge.
    """
    return [{
        "date": date_str,
        "revenue": 4120.21,
        "units": 291.0,
        "sessions": 2510.0,
        "cvr": 11.6,
        "spend": 900.0,
        "ventasPPC": 2000.0,
        "days_covered": 25,
        "partial": partial,
    }]


def _mes_en_curso() -> str:
    """El mes de HOY como fecha de fila. `_resolve_partial` compara contra esto."""
    t = date.today()
    return f"{t.year:04d}-{t.month:02d}-01"


def _actual_traces(fig) -> list:
    """Los traces de la capa `actual` de una figura (los que dicen '(real)')."""
    return [t for t in fig.data if t.name and t.name.endswith("(real)")]


def test_export_with_actual_adds_one_real_trace_per_metric():
    """Los 7 charts suman su línea real: 4 de 1 métrica + Ads(2) + ACOS(2) + Custom(1)."""
    con = _build_export_html(_cur(), actual_rows=_actual())
    assert con.count("(real)") == 9


def test_export_without_actual_has_no_real_line():
    """None / [] / omitido → el reporte sale como antes de A4 (no-regresión)."""
    omitido = _build_export_html(_cur())
    nulo = _build_export_html(_cur(), actual_rows=None)
    vacio = _build_export_html(_cur(), actual_rows=[])
    for h in (omitido, nulo, vacio):
        assert "(real)" not in h
    # Mismo conteo de líneas dibujadas en los tres → ningún trace de más ni de menos.
    n = omitido.count("lines+markers")
    assert nulo.count("lines+markers") == n
    assert vacio.count("lines+markers") == n
    # Y con actual hay 9 más, uno por métrica real.
    assert _build_export_html(_cur(), actual_rows=_actual()).count("lines+markers") == n + 9


def test_export_with_actual_labels_the_line_as_real():
    """El deliverable dice explícitamente cuál línea es la real."""
    con = _build_export_html(_cur(), actual_rows=_actual())
    assert "Revenue (real)" in con
    assert "Spend (real)" in con


def test_export_ads_second_actual_is_washed():
    """Ads: 1ra real (spend) verde sólido, 2da (ventasPPC) washed.

    En un screenshot del reporte no hay hover — dos verdes idénticas serían
    indistinguibles.
    """
    fig = _ads_chart(_hist(), _fc(), False, actual_rows=_actual())
    reales = _actual_traces(fig)
    assert len(reales) == 2
    assert reales[0].line.color == _CHART_ACTUAL
    assert reales[1].line.color == _CHART_ACTUAL_WASHED
    assert reales[0].line.color != reales[1].line.color


def test_export_acos_second_actual_is_washed():
    """ACOS/TACOS: misma regla que Ads (1ra sólida, 2da washed)."""
    fig = _acos_tacos_chart(_hist(), _fc(), False, actual_rows=_actual())
    reales = _actual_traces(fig)
    assert len(reales) == 2
    assert reales[0].line.color == _CHART_ACTUAL
    assert reales[1].line.color == _CHART_ACTUAL_WASHED


def test_export_custom_second_actual_is_washed():
    """Custom con 2+ métricas: misma regla que Ads. La 1ra es la del catálogo."""
    fig = _custom_chart(["revenue", "sessions"], _hist(), _fc(), False,
                        actual_rows=_actual())
    reales = _actual_traces(fig)
    assert len(reales) == 2
    assert reales[0].line.color == _CHART_ACTUAL
    assert reales[1].line.color == _CHART_ACTUAL_WASHED


def test_single_metric_chart_actual_stays_solid():
    """Los charts de UNA métrica no se tocan: su única línea real sigue sólida.

    Se verifica sobre la FIGURA y no sobre el HTML del reporte: el export arma
    los 7 charts, y Ads/ACOS siempre aportan un washed → el documento entero
    contiene el color washed pase lo que pase.
    """
    fig = _metric_chart("revenue", _hist(), _fc(), False, actual_rows=_actual())
    reales = _actual_traces(fig)
    assert len(reales) == 1
    assert reales[0].line.color == _CHART_ACTUAL


def test_export_washed_color_reaches_the_html():
    """El washed sobrevive hasta el documento (no se pierde al serializar)."""
    con = _build_export_html(_cur(), actual_rows=_actual())
    assert _CHART_ACTUAL_WASHED in con


def test_export_resolves_partial_internally():
    """D1 — el export cierra el `partial=None` solo; el caller pasa el dato crudo.

    `partial=None` (BR mensual, cobertura desconocida) en el mes EN CURSO tiene
    que terminar dibujado como parcial → marcador `circle-open`.
    """
    crudo = _actual(_mes_en_curso(), partial=None)
    assert crudo[0]["partial"] is None          # entra sin resolver
    con = _build_export_html(_cur(), actual_rows=crudo)
    assert "circle-open" in con


def test_export_partial_none_on_closed_month_is_not_marked():
    """Control del anterior: `None` en un mes CERRADO no se pinta como parcial."""
    con = _build_export_html(_cur(), actual_rows=_actual("2026-03-01", partial=None))
    assert "(real)" in con                      # la línea está…
    assert "circle-open" not in con             # …pero sin anillo de parcial


def test_export_custom_order_is_catalog_not_buffer():
    """El Custom del reporte respeta el orden de catálogo, como la pantalla (G5).

    El buffer de chips guarda el orden en que el AM los tocó. Ese orden decide
    qué línea real va sólida y cuál es el eje izquierdo, así que el reporte tiene
    que normalizarlo igual que G5 o sale distinto del que el AM validó.
    """
    al_reves = _build_export_html(_cur(), custom_metrics=["sessions", "revenue"],
                                  actual_rows=_actual())
    en_orden = _build_export_html(_cur(), custom_metrics=["revenue", "sessions"],
                                  actual_rows=_actual())
    assert al_reves.count("(real)") == en_orden.count("(real)")
    assert al_reves.count(_CHART_ACTUAL_WASHED) == en_orden.count(_CHART_ACTUAL_WASHED)


# ─────────────────────────────────────────────────────────────────────────────
# _asin_table_html — tabla por-ASIN del export (E7, pieza 1)
# ─────────────────────────────────────────────────────────────────────────────
#
# Se construye desde los dicts del modelo, NO desde los df builders de la app:
# el HTML va a un documento que se manda por mail, así que necesita formato con
# currency y `html.escape` en todo string que venga de datos (los títulos los
# escribe Amazon y traen `&` seguido).

def _asin_node(parent, title, rev_by_period):
    return {
        "parent_asin": parent,
        "title": title,
        "history": [
            {"period": p, "revenue": r, "units": 10.0, "sessions": 100.0,
             "unit_session_pct": 10.0, "page_views": 120.0, "buy_box_pct": 90.0}
            for p, r in sorted(rev_by_period.items())
        ],
    }


def _asin_model_2x2():
    """2 ASINs x 2 períodos, con el padre real presente."""
    return {
        "B00PARENT": _asin_node("B00PARENT", "Producto Padre",
                                {"2026-06": 1000.0, "2026-07": 1500.0}),
        "B00CHILD1": _asin_node("B00PARENT", "Variante Roja",
                                {"2026-06": 500.0, "2026-07": 2000.0}),
    }


# nivel child

def test_asin_table_child_one_row_per_asin():
    out = _asin_table_html(_asin_model_2x2(), "child")
    assert out.count("<tr>") == 3          # 1 header + 2 ASINs
    assert "B00PARENT" in out and "B00CHILD1" in out


def test_asin_table_child_has_period_columns():
    out = _asin_table_html(_asin_model_2x2(), "child")
    assert "<th>2026-06</th>" in out
    assert "<th>2026-07</th>" in out


def test_asin_table_child_formats_revenue_as_currency():
    """Revenue formateado, no float crudo."""
    out = _asin_table_html(_asin_model_2x2(), "child")
    assert "$1,000" in out
    assert ">1000.0<" not in out


def test_asin_table_child_missing_period_is_dash():
    """ASIN sin dato en un mes queda em-dash, igual que _forecast_table_html."""
    model = {
        "B00A": _asin_node("B00A", "A", {"2026-06": 100.0}),
        "B00B": _asin_node("B00B", "B", {"2026-07": 200.0}),
    }
    assert "—" in _asin_table_html(model, "child")


def test_asin_table_child_sorted_by_latest_revenue_desc():
    """El que más factura en el último mes va primero."""
    out = _asin_table_html(_asin_model_2x2(), "child")
    assert out.index("B00CHILD1") < out.index(">B00PARENT<")


# nivel parent

def test_asin_table_parent_uses_real_parent_title():
    """Mismo criterio E5 que la app (fuente única: _asin_parent_agg)."""
    out = _asin_table_html(_asin_model_2x2(), "parent")
    assert "Producto Padre" in out
    assert "Variante Roja" not in out


def test_asin_table_parent_falls_back_to_first_child_title():
    model = {
        "B00C1": _asin_node("B00P9", "Primera Variante", {"2026-06": 100.0}),
        "B00C2": _asin_node("B00P9", "Segunda Variante", {"2026-06": 200.0}),
    }
    assert "Primera Variante" in _asin_table_html(model, "parent")


def test_asin_table_parent_sums_children_revenue():
    """La fila parent suma los childs: 1000 + 500 en junio."""
    out = _asin_table_html(_asin_model_2x2(), "parent")
    assert "$1,500" in out
    assert out.count("<tr>") == 2          # 1 header + 1 parent


def test_asin_table_parent_empty_parent_shows_placeholder():
    """parent_asin vacío queda como placeholder, no celda en blanco."""
    model = {"B00A": _asin_node("", "Suelto", {"2026-06": 100.0})}
    assert "Sin parent" in _asin_table_html(model, "parent")


def test_asin_table_child_empty_parent_shows_placeholder():
    """Mismo placeholder en la columna Parent ASIN del nivel child."""
    model = {"B00A": _asin_node("", "Suelto", {"2026-06": 100.0})}
    assert "Sin parent" in _asin_table_html(model, "child")


# nivel cuenta

def test_asin_table_cuenta_one_row_per_period():
    out = _asin_table_html(_asin_model_2x2(), "cuenta")
    assert out.count("<tr>") == 3          # 1 header + 2 períodos
    assert "2026-06" in out and "2026-07" in out


def test_asin_table_cuenta_totals_revenue_units_sessions():
    """Junio: 1000 + 500 revenue, units 20, sessions 200."""
    out = _asin_table_html(_asin_model_2x2(), "cuenta")
    for header in ("Revenue", "Units", "Sessions"):
        assert f"<th>{header}</th>" in out
    assert "$1,500" in out
    assert ">20<" in out and ">200<" in out


# seguridad: escape

def test_asin_table_escapes_title_ampersand_and_lt():
    """LOAD-BEARING. Los títulos los escribe Amazon y van a un doc por mail.

    Sin html.escape, un título con < inyecta markup en el deliverable.
    """
    model = {"B00A": _asin_node("B00A", "Crema A & B <Night>", {"2026-06": 10.0})}
    out = _asin_table_html(model, "child")
    assert "&amp;" in out
    assert "&lt;Night&gt;" in out
    assert "A & B <Night>" not in out


def test_asin_table_escapes_title_at_parent_level():
    model = {"B00A": _asin_node("B00A", "Marca & Co", {"2026-06": 10.0})}
    out = _asin_table_html(model, "parent")
    assert "&amp;" in out
    assert "Marca & Co" not in out


def test_asin_table_escapes_asin_field():
    """El ASIN también sale de datos: se escapa igual que el título."""
    model = {"<script>": _asin_node("<script>", "T", {"2026-06": 10.0})}
    out = _asin_table_html(model, "child")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


# bordes

def test_asin_table_empty_model_returns_empty_string():
    """Igual que _forecast_table_html: vacío y el caller omite la sección."""
    for level in ("child", "parent", "cuenta"):
        assert _asin_table_html({}, level) == ""


def test_asin_table_model_without_history_returns_empty_string():
    model = {"B00A": {"parent_asin": "B00A", "title": "T", "history": []}}
    for level in ("child", "parent", "cuenta"):
        assert _asin_table_html(model, level) == ""


def test_asin_table_single_period_works():
    model = {"B00A": _asin_node("B00A", "T", {"2026-06": 100.0})}
    out = _asin_table_html(model, "child")
    assert "<th>2026-06</th>" in out
    assert "$100" in out


def test_asin_table_respects_currency():
    """currency se propaga a _fmt_currency (no hardcodea la moneda)."""
    model = {"B00A": _asin_node("B00A", "T", {"2026-06": 1000.0})}
    assert "$1,000" in _asin_table_html(model, "child", currency="MXN")


def test_asin_table_invalid_level_raises():
    """Typo en level falla fuerte: devolver vacío dejaría una sección muda."""
    with pytest.raises(ValueError, match="level inválido"):
        _asin_table_html(_asin_model_2x2(), "chid")


def test_asin_table_no_plotly_in_output():
    """LOAD-BEARING (tamaño). La vista por-ASIN es SOLO tabla.

    Decisión de producto: nada de charts por ASIN. 64 ASINs x chart infla el
    HTML y Gmail rebota adjuntos grandes. Si esto falla, alguien metió una
    figura acá y el export dejó de ser mailable.
    """
    out = _asin_table_html(_asin_model_2x2(), "child")
    assert "plotly" not in out.lower()
    assert "cdn.plot.ly" not in out


# ─────────────────────────────────────────────────────────────────────────────
# _build_export_html + asin_model — sección "Detalle por ASIN" (E7, pieza 3)
# ─────────────────────────────────────────────────────────────────────────────
#
# Sección APILADA, sin tabs ni JS: el reporte se abre y se le saca screenshot,
# así que una pestaña oculta sería contenido que nadie captura. Sólo niveles
# Parent + Cuenta (el child con N ASINs es ruido para el cliente).

def _export_asin_model():
    return {
        "B00PARENT": _asin_node("B00PARENT", "Producto Padre",
                                {"2026-06": 1000.0, "2026-07": 1500.0}),
        "B00CHILD1": _asin_node("B00PARENT", "Variante Roja",
                                {"2026-06": 500.0, "2026-07": 2000.0}),
    }


# ── retrocompatibilidad ──────────────────────────────────────────────────────

def test_export_without_asin_model_has_no_asin_section():
    """Default None → el reporte sale como antes de E7, sin la sección."""
    out = _build_export_html(_cur())
    assert "Detalle por ASIN" not in out
    assert "Por producto (Parent)" not in out
    assert "Total por mes (Cuenta)" not in out


def test_export_explicit_none_asin_model_has_no_asin_section():
    assert "Detalle por ASIN" not in _build_export_html(_cur(), asin_model=None)


def test_export_empty_asin_model_has_no_asin_section():
    """Modelo vacío se trata como ausente: no emite una sección en blanco."""
    assert "Detalle por ASIN" not in _build_export_html(_cur(), asin_model={})


def test_export_asin_model_without_history_has_no_asin_section():
    """Modelo sin períodos → las tablas dan '' → la sección no se emite."""
    model = {"B00A": {"parent_asin": "B00A", "title": "T", "history": []}}
    assert "Detalle por ASIN" not in _build_export_html(_cur(), asin_model=model)


# ── con modelo ───────────────────────────────────────────────────────────────

def test_export_with_asin_model_adds_section():
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert "Detalle por ASIN" in out
    assert "Por producto (Parent)" in out
    assert "Total por mes (Cuenta)" in out


def test_export_asin_section_has_parent_and_account_data():
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert "B00PARENT" in out
    assert "Producto Padre" in out
    assert "$1,500" in out          # junio: 1000 + 500 sumados en el parent


def test_export_asin_section_omits_child_level():
    """Decisión de producto: child NO va (9-64 ASINs = ruido para el cliente).

    El título de la variante sólo existe a nivel child; si aparece, alguien
    agregó ese nivel al export.
    """
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert "Variante Roja" not in out
    assert "Child ASIN" not in out


def test_export_asin_section_comes_before_footer():
    """La sección va apilada al final del contenido, antes del footer."""
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert out.index("Detalle por ASIN") < out.index("Generado por Agency OS")


def test_export_asin_section_after_forecast_detail():
    """Orden: el detalle por-cuenta primero, el por-ASIN después."""
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert out.index("Detalle del forecast") < out.index("Detalle por ASIN")


# ── LOAD-BEARING: mailability ────────────────────────────────────────────────

def test_export_with_asin_model_still_seven_charts():
    """🔴 LOAD-BEARING. La sección ASIN es SÓLO tablas: no suma figuras."""
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert out.count("plotly-graph-div") == 7


def test_export_with_asin_model_still_loads_plotly_once():
    """🔴 LOAD-BEARING (tamaño). Con modelo, plotly.js se sigue cargando 1 vez.

    Si esto da >1, alguien metió una figura en la sección por-ASIN y el reporte
    pasó a pesar decenas de MB: Gmail rebota el adjunto.
    """
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert out.count("cdn.plot.ly") == 1


def test_export_asin_section_has_no_script_tags():
    """Sin tabs = sin JS. El deliverable no debe traer <script> propio.

    (Plotly inyecta los suyos; lo que se blinda acá es que la sección ASIN no
    agregue lógica de pestañas.)
    """
    out = _build_export_html(_cur(), asin_model=_export_asin_model())
    assert "tab-panel" not in out
    assert "onclick" not in out


# ── escape end-to-end ────────────────────────────────────────────────────────

def test_export_escapes_asin_title_end_to_end():
    """🔴 El título de Amazon llega escapado al documento final, no sólo en el
    helper aislado."""
    model = {"B00A": _asin_node("B00A", "Crema A & B <Night>", {"2026-06": 10.0})}
    out = _build_export_html(_cur(), asin_model=model)
    assert "&amp;" in out
    assert "&lt;Night&gt;" in out
    assert "A & B <Night>" not in out


def test_export_asin_respects_account_currency():
    """La sección ASIN usa la moneda de la cuenta, no una hardcodeada."""
    model = {"B00A": _asin_node("B00A", "T", {"2026-06": 1000.0})}
    out = _build_export_html(_cur(currency="MXN"), asin_model=model)
    assert "$1,000" in out


# ─────────────────────────────────────────────────────────────────────────────
# include_general — los 3 casos del selector de vistas (E8, pieza 4)
# ─────────────────────────────────────────────────────────────────────────────
#
# El AM elige qué mandar: sólo la proyección general, sólo el detalle por ASIN,
# o las dos. El caso "ninguna" lo ataja la UI antes de llamar acá (no se ofrece
# la descarga), pero el helper igual no debe romper.

def test_export_include_general_default_is_true():
    """Sin pasar el param, el reporte sale completo — retrocompat."""
    out = _build_export_html(_cur())
    assert out.count("plotly-graph-div") == 7
    assert "Resumen de la proyección" in out
    assert "Detalle del forecast" in out


# ── caso 1: sólo general ─────────────────────────────────────────────────────

def test_export_only_general_has_no_asin_section():
    out = _build_export_html(_cur(), include_general=True, asin_model=None)
    assert out.count("plotly-graph-div") == 7
    assert "Detalle por ASIN" not in out


# ── caso 2: ambos ────────────────────────────────────────────────────────────

def test_export_both_views_has_charts_and_asin():
    out = _build_export_html(_cur(), include_general=True,
                             asin_model=_export_asin_model())
    assert out.count("plotly-graph-div") == 7
    assert "Resumen de la proyección" in out
    assert "Detalle por ASIN" in out


# ── caso 3: sólo ASIN ────────────────────────────────────────────────────────

def test_export_only_asin_omits_general_content():
    """include_general=False saca resumen + charts + detalle de cuenta."""
    out = _build_export_html(_cur(), include_general=False,
                             asin_model=_export_asin_model())
    assert "Resumen de la proyección" not in out
    assert "Detalle del forecast" not in out
    assert "Detalle por ASIN" in out


def test_export_only_asin_has_zero_charts():
    """🔴 Sin proyección general no hay NINGÚN chart: el reporte más liviano.

    Y sin charts tampoco se carga plotly.js — el documento pesa unos KB.
    """
    out = _build_export_html(_cur(), include_general=False,
                             asin_model=_export_asin_model())
    assert out.count("plotly-graph-div") == 0
    assert out.count("cdn.plot.ly") == 0


def test_export_only_asin_keeps_header_and_footer():
    """Sigue siendo un documento con marca, no un fragmento suelto."""
    out = _build_export_html(_cur(), include_general=False,
                             asin_model=_export_asin_model())
    assert out.startswith("<!DOCTYPE html>")
    assert "Capybaras" in out
    assert "Dermaglos" in out
    assert "Generado por Agency OS" in out


def test_export_only_asin_keeps_note():
    """La nota del AM va igual: no depende de la vista general."""
    out = _build_export_html(_cur(), note="Contexto del mes.",
                             include_general=False,
                             asin_model=_export_asin_model())
    assert "Contexto del mes." in out
    assert 'class="note"' in out


def test_export_only_asin_works_without_account_history():
    """Sin histórico de cuenta pero CON modelo por-ASIN, no cae al doc mínimo.

    La UI no permite llegar acá (el gate de forecast lo impide), pero el helper
    es puro y no debe romper ni devolver 'Sin datos' teniendo qué mostrar.
    """
    out = _build_export_html(_cur(historical=[], forecast=[]),
                             include_general=False,
                             asin_model=_export_asin_model())
    assert "Detalle por ASIN" in out
    assert "Sin datos para exportar" not in out


def test_export_no_views_selected_is_minimal_not_crash():
    """Caso que la UI previene: sin general y sin ASIN, no revienta."""
    out = _build_export_html(_cur(), include_general=False, asin_model=None)
    assert out.startswith("<!DOCTYPE html>")
    assert "</html>" in out
    assert out.count("plotly-graph-div") == 0
    assert "Detalle por ASIN" not in out

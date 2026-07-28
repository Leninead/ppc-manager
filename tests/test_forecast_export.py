"""M31 · G6 — Tests del export HTML self-contained.

Puros: operan sobre el string HTML devuelto por la capa pura. Sin runtime de
Streamlit, sin session_state, sin browser.

`_build_export_html` recibe `show_yoy` como parámetro (default True) justamente
para que estos tests NO dependan del buffer de G5 en session_state.
"""

from datetime import date

from modules.pages.revenue_forecast import (
    _CHART_ACTUAL,
    _CHART_ACTUAL_WASHED,
    _acos_tacos_chart,
    _ads_chart,
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

"""M31 · G6 — Tests del export HTML self-contained.

Puros: operan sobre el string HTML devuelto por la capa pura. Sin runtime de
Streamlit, sin session_state, sin browser.

`_build_export_html` recibe `show_yoy` como parámetro (default True) justamente
para que estos tests NO dependan del buffer de G5 en session_state.
"""

from modules.pages.revenue_forecast import (
    _build_export_html,
    _cliente_slug,
    _forecast_table_html,
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


def test_export_show_yoy_toggle_changes_output():
    """El reporte RESPETA el toggle del AM: con/sin YoY el HTML difiere."""
    on = _build_export_html(_cur(), show_yoy=True)
    off = _build_export_html(_cur(), show_yoy=False)
    assert on != off

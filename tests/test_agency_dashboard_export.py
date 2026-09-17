"""Tests B3b — export HTML del Dashboard Global (M39).

`_build_agency_html` es PURA: recibe el dict que devuelve
`_build_agency_dashboard` y devuelve un string. No toca disco, no lee
session_state y no llama a `date.today()` (la fecha entra por parámetro), así
que se testea directo, sin AppTest.

El wiring del botón de descarga sí va por AppTest, mínimo.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core import agency_dashboard_export as exp
from core import agency_dashboard_format as fmt


_REPO_ROOT = str(Path(__file__).resolve().parents[1])
_GEN = date(2026, 9, 16)


# ─────────────────────────────────────────────────────────────────────────────
# Datos de prueba
# ─────────────────────────────────────────────────────────────────────────────

def _cell(actual=None, acco=None, partial=None) -> dict:
    keys = ("revenue", "ventasPPC", "spend", "acos", "tacos")
    return {
        "actual": actual,
        "forecast": None,
        "accomplishment": {k: (acco or {}).get(k) for k in keys},
        "partial": partial,
    }


_ACTUAL = {"revenue": 9000.0, "ventasPPC": 3000.0, "spend": 900.0,
           "acos": 30.0, "tacos": 10.0}


def _account(name="Alpha Brand", client_id="alpha", has_baseline=True,
             months=None, currency="USD") -> dict:
    return {
        "client_id": client_id,
        "name": name,
        "currency": currency,
        "has_baseline": has_baseline,
        "baseline_name": "Plan 2026" if has_baseline else None,
        "baseline_created_at": "2026-09-01" if has_baseline else None,
        "months": months or {
            "2026-08": _cell(actual=_ACTUAL, acco={"revenue": 95.0, "acos": -1.0},
                             partial=False),
        },
    }


def _dash(accounts, periods=("2026-08",)) -> dict:
    return {"periods": list(periods), "accounts": accounts}


# ─────────────────────────────────────────────────────────────────────────────
# Documento
# ─────────────────────────────────────────────────────────────────────────────

def test_sin_cuentas_devuelve_documento_valido_con_mensaje():
    html = exp._build_agency_html(_dash([]), generated_at=_GEN)
    assert html.lower().startswith("<!doctype html>")
    assert "</html>" in html
    assert "sin cuentas" in html.lower()
    assert "<table" not in html


def test_dos_cuentas_con_indice_y_anclas():
    dash = _dash([_account(name="Alpha Brand", client_id="alpha"),
                  _account(name="Beta Labs", client_id="beta")])
    html = exp._build_agency_html(dash, generated_at=_GEN)

    assert "Alpha Brand" in html and "Beta Labs" in html
    # Índice: un link por cuenta, apuntando a su ancla.
    assert html.count('<a href="#') == 2
    for slug in ("alpha", "beta"):
        assert f'href="#cuenta-{slug}"' in html
        assert f'id="cuenta-{slug}"' in html
    # Una tabla por cuenta, apiladas.
    assert html.count("<table") == 2


def test_orden_de_las_cuentas_es_el_de_la_data():
    """El agregador ya las ordena alfabéticamente; el export NO reordena."""
    dash = _dash([_account(name="Alpha Brand", client_id="alpha"),
                  _account(name="Beta Labs", client_id="beta")])
    html = exp._build_agency_html(dash, generated_at=_GEN)
    assert html.index("Alpha Brand") < html.index("Beta Labs")


def test_header_trae_rango_de_meses_y_fecha_de_generacion():
    dash = _dash([_account()], periods=("2026-08", "2026-09"))
    html = exp._build_agency_html(dash, generated_at=_GEN)
    assert "2026-08" in html and "2026-09" in html
    assert "2026-09-16" in html
    assert "Dashboard Global" in html


def test_footer_capybaras():
    html = exp._build_agency_html(_dash([_account()]), generated_at=_GEN)
    assert "Capybaras" in html


# ─────────────────────────────────────────────────────────────────────────────
# Semáforo — que reuse el de la pantalla, no uno propio
# ─────────────────────────────────────────────────────────────────────────────

def _celda_color(html: str, texto: str) -> str:
    """Color de fondo de la celda que contiene `texto`."""
    import re
    m = re.search(r'<td[^>]*background-color:\s*(#[0-9A-Fa-f]{6})[^>]*>' + re.escape(texto),
                  html)
    return m.group(1) if m else ""


def test_colores_del_semaforo_en_las_celdas_acco():
    dash = _dash([_account(months={
        "2026-08": _cell(actual=_ACTUAL, acco={"revenue": 95.0}, partial=False),
        "2026-09": _cell(actual=_ACTUAL, acco={"revenue": 78.0, "acos": 3.0},
                         partial=False),
    })], periods=("2026-08", "2026-09"))
    html = exp._build_agency_html(dash, generated_at=_GEN)

    assert _celda_color(html, "95.0%").upper() == fmt._VERDE.upper()
    assert _celda_color(html, "78.0%").upper() == fmt._ROJO.upper()
    assert _celda_color(html, "+3.0").upper() == fmt._ROJO.upper()


def test_acos_en_el_target_va_verde_no_amarillo():
    """El fix de 7e0767c tiene que valer también en el export."""
    dash = _dash([_account(months={
        "2026-08": _cell(actual=_ACTUAL, acco={"acos": 1.3e-06}, partial=False)})])
    html = exp._build_agency_html(dash, generated_at=_GEN)
    assert _celda_color(html, "+0.0").upper() == fmt._VERDE.upper()


def test_celdas_sin_dato_no_llevan_color():
    dash = _dash([_account(has_baseline=False, months={
        "2026-08": _cell(actual=_ACTUAL, partial=False)})])
    html = exp._build_agency_html(dash, generated_at=_GEN)
    for color in (fmt._VERDE, fmt._AMARILLO, fmt._ROJO):
        assert color.lower() not in html.lower().split("<style>")[-1].split("</style>")[-1]


# ─────────────────────────────────────────────────────────────────────────────
# Cuentas sin plan y mes en curso
# ─────────────────────────────────────────────────────────────────────────────

def test_cuenta_sin_baseline_marcada_en_el_indice_y_en_su_seccion():
    dash = _dash([_account(name="Zeta Corp", client_id="zeta", has_baseline=False)])
    html = exp._build_agency_html(dash, generated_at=_GEN)
    assert html.lower().count("sin plan") >= 2      # índice + sección


def test_cuenta_con_baseline_muestra_el_plan():
    html = exp._build_agency_html(_dash([_account()]), generated_at=_GEN)
    assert "Plan 2026" in html
    assert "2026-09-01" in html


def test_mes_en_curso_marcado_y_nota_al_pie():
    con = _dash([_account(months={
        "2026-09": _cell(actual=_ACTUAL, partial=True)})], periods=("2026-09",))
    sin = _dash([_account(months={
        "2026-09": _cell(actual=_ACTUAL, partial=False)})], periods=("2026-09",))
    html_con = exp._build_agency_html(con, generated_at=_GEN)
    html_sin = exp._build_agency_html(sin, generated_at=_GEN)
    assert "Sep*" in html_con and "MtD" in html_con
    assert "Sep*" not in html_sin and "MtD" not in html_sin


# ─────────────────────────────────────────────────────────────────────────────
# Seguridad y standalone
# ─────────────────────────────────────────────────────────────────────────────

def test_nombre_de_cuenta_con_html_sale_escapado():
    dash = _dash([_account(name="<script>alert(1)</script>", client_id="xss")])
    html = exp._build_agency_html(dash, generated_at=_GEN)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_nombre_de_snapshot_con_html_sale_escapado():
    acc = _account()
    acc["baseline_name"] = 'Plan "A" & <b>B</b>'
    html = exp._build_agency_html(_dash([acc]), generated_at=_GEN)
    assert "<b>B</b>" not in html
    assert "&lt;b&gt;" in html


def test_documento_standalone_sin_red_ni_js():
    dash = _dash([_account(name="Alpha"), _account(name="Beta", client_id="beta")])
    html = exp._build_agency_html(dash, generated_at=_GEN)
    bajo = html.lower()
    assert "<!doctype" in bajo
    assert "<style>" in bajo
    assert "http://" not in bajo and "https://" not in bajo
    assert "<script" not in bajo
    assert "<link" not in bajo
    # Nada heredado del export de M31.
    assert "fonts.googleapis" not in bajo
    assert "fonts.gstatic" not in bajo
    assert "cdn" not in bajo
    assert "plotly" not in bajo


def test_font_family_usa_stack_del_sistema():
    html = exp._build_agency_html(_dash([_account()]), generated_at=_GEN)
    assert "-apple-system" in html or "Segoe UI" in html


def test_documento_es_determinista():
    dash = _dash([_account(name="Alpha"), _account(name="Beta", client_id="beta")])
    a = exp._build_agency_html(dash, generated_at=_GEN)
    b = exp._build_agency_html(dash, generated_at=_GEN)
    assert a == b


def test_generated_at_por_default_no_explota():
    html = exp._build_agency_html(_dash([_account()]))
    assert html.lower().startswith("<!doctype html>")


# ─────────────────────────────────────────────────────────────────────────────
# Wiring del botón en la página
# ─────────────────────────────────────────────────────────────────────────────

_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import agency_dashboard_page as page

page._build_agency_dashboard = lambda periods, clients=None: __DASH__
page.render(username="quien", role="admin")
"""


def _run(dash_repr: str) -> AppTest:
    at = AppTest.from_string(
        _APP.replace("__REPO_ROOT__", _REPO_ROOT).replace("__DASH__", dash_repr)
    )
    at.run()
    return at


def test_boton_de_descarga_presente_con_cuentas():
    """El de HTML. El conteo total de botones lo fija
    `test_agency_dashboard_excel.py`, que es donde se agregó el segundo."""
    at = _run(repr(_dash([_account()], periods=("2026-08",))))
    assert not at.exception
    labels = [b.proto.label for b in at.get("download_button")]
    assert any("HTML" in l for l in labels), labels


def test_sin_cuentas_no_hay_boton():
    at = _run(repr(_dash([], periods=("2026-08",))))
    assert not at.exception
    assert len(at.get("download_button")) == 0


def test_leyenda_del_desvio_en_el_html():
    """Ajuste A: la misma leyenda que la pantalla y la planilla."""
    html = exp._build_agency_html(_dash([_account()]), generated_at=_GEN)
    assert "desv" in html and "real − plan" in html
    # Aparece aunque ninguna cuenta tenga mes en curso (no depende del MtD).
    assert "MtD" not in html

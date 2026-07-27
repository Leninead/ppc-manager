"""M31 F7-A3 — wiring de la capa `actual`: resolución de `partial` contra hoy.

A1 dejó `partial` como TRI-ESTADO a propósito: `True`/`False` cuando el BR vino
diario y la cobertura era medible, `None` cuando vino mensual (Amazon ya agregó y
no hay forma de saber cuántos días cubre). El helper de A1 es PURO — no llama a
`date.today()`.

Acá se cierra ese `None`, que es lo único de la capa que necesita saber qué día
es hoy: el mes EN CURSO es parcial, un mes pasado está cerrado.

El resto de A3 es wiring de Streamlit (uploader + `actual_rows=` en los 7 charts)
y no se testea sin runtime — lo verifica el smoke visual.
"""

from __future__ import annotations

from datetime import date

from modules.pages import revenue_forecast as rf


_HOY = date(2026, 8, 12)          # agosto 2026, a mitad de mes
_MES_ACTUAL = "2026-08-01"
_MES_PASADO = "2026-07-01"
_MES_FUTURO = "2026-09-01"


def _row(fecha: str, partial):
    return {"date": fecha, "revenue": 100.0, "partial": partial}


# ─────────────────────────────────────────────────────────────────────────────
# Resolución del None (BR mensual)
# ─────────────────────────────────────────────────────────────────────────────

def test_none_en_el_mes_en_curso_es_parcial():
    out = rf._resolve_partial([_row(_MES_ACTUAL, None)], today=_HOY)
    assert out[0]["partial"] is True


def test_none_en_un_mes_pasado_esta_cerrado():
    """Un BR By Month de julio bajado en agosto es un mes CERRADO. Marcarlo
    parcial sería dato engañoso hacia el cliente — el motivo por el que A1 dejó
    el `None` sin resolver en vez de asumir `True`.
    """
    out = rf._resolve_partial([_row(_MES_PASADO, None)], today=_HOY)
    assert out[0]["partial"] is False


def test_none_en_un_mes_futuro_no_es_parcial():
    """Un mes que todavía no arrancó no es 'en curso'. Sólo el mes de hoy."""
    out = rf._resolve_partial([_row(_MES_FUTURO, None)], today=_HOY)
    assert out[0]["partial"] is False


def test_row_sin_la_key_partial_se_resuelve_igual():
    """Filas cargadas antes de F7-A (o a mano) no traen la key. `.get` → None →
    se resuelve contra hoy como cualquier otro desconocido.
    """
    out = rf._resolve_partial([{"date": _MES_ACTUAL, "revenue": 100.0}], today=_HOY)
    assert out[0]["partial"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Lo que A1 ya sabía NO se pisa
# ─────────────────────────────────────────────────────────────────────────────

def test_true_de_a1_se_respeta():
    """BR diario de un mes pasado con cobertura incompleta (el AM subió julio a
    los 20 días y nunca lo completó): sigue siendo parcial aunque julio ya cerró.
    Es la verdad del DATO, y A1 la midió. Hoy no la pisa.
    """
    out = rf._resolve_partial([_row(_MES_PASADO, True)], today=_HOY)
    assert out[0]["partial"] is True


def test_false_de_a1_se_respeta():
    """Mes en curso con los días completos no existe en la práctica, pero si A1
    midió cobertura completa, hoy no la contradice.
    """
    out = rf._resolve_partial([_row(_MES_ACTUAL, False)], today=_HOY)
    assert out[0]["partial"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Contratos
# ─────────────────────────────────────────────────────────────────────────────

def test_no_muta_el_input():
    """Devuelve COPIAS: `cur["actual"]` es el dato persistido del cliente y no
    debe quedar contaminado con un flag derivado de la fecha de HOY (mañana la
    respuesta cambia).
    """
    original = [_row(_MES_ACTUAL, None)]
    out = rf._resolve_partial(original, today=_HOY)

    assert original[0]["partial"] is None      # intacto
    assert out[0]["partial"] is True
    assert out[0] is not original[0]


def test_lista_vacia_devuelve_vacia():
    assert rf._resolve_partial([], today=_HOY) == []


def test_conserva_el_resto_de_los_campos_y_el_orden():
    rows = [
        {"date": _MES_PASADO, "revenue": 100.0, "spend": 10.0, "partial": None},
        {"date": _MES_ACTUAL, "revenue": 50.0, "spend": 5.0, "partial": None},
    ]
    out = rf._resolve_partial(rows, today=_HOY)

    assert [r["date"] for r in out] == [_MES_PASADO, _MES_ACTUAL]
    assert out[0]["spend"] == 10.0 and out[1]["spend"] == 5.0
    assert [r["partial"] for r in out] == [False, True]


def test_today_por_defecto_usa_la_fecha_real():
    """Sin `today` inyectado cae en `date.today()` — es el uso de producción.
    Se verifica contra el mes real de hoy, sin clavar una fecha.
    """
    hoy = date.today()
    mes_de_hoy = f"{hoy.year:04d}-{hoy.month:02d}-01"
    out = rf._resolve_partial([_row(mes_de_hoy, None)])
    assert out[0]["partial"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Integración con la salida real de A1
# ─────────────────────────────────────────────────────────────────────────────

_SYNTH_MENSUAL = """\
Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage
2026-07-01,"$50,000.00",500,5000,10.00%
"""


def test_cierra_el_none_que_deja_el_parser_de_a1():
    """End-to-end de la decisión: `_parse_actual_report` deja `None` para el BR
    mensual y `_resolve_partial` lo cierra. Las dos piezas encajan.
    """
    rows = rf._parse_actual_report(_SYNTH_MENSUAL.encode("utf-8"), "mensual.csv")
    assert rows[0]["partial"] is None                     # A1: no adivina

    resuelto = rf._resolve_partial(rows, today=_HOY)      # agosto → julio cerrado
    assert resuelto[0]["partial"] is False

    en_julio = rf._resolve_partial(rows, today=date(2026, 7, 20))
    assert en_julio[0]["partial"] is True

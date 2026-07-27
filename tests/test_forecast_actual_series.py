"""M31 F7-A1 — helpers puros de la capa `actual` (Real vs Forecast, nivel cuenta).

Contexto: Eduardo pidió ver el REAL del mes corriendo contra el FORECAST como
evolutivo (mes a mes). La capa `actual` es una TERCERA serie que CONVIVE con
`historical` y `forecast` — no pisa ninguna de las dos.

Hallazgo que ordena el diseño: las filas de `actual` salen del MISMO Business
Report que `historical` → MISMO shape → los accessors `from_hist` de las 10
métricas de `_METRICS` funcionan tal cual. Cero accessors nuevos.

Helpers bajo test:
    _read_br_rows          — extract aditivo de _parse_business_report (granularidad ORIGINAL)
    _count_days_by_month   — días DISTINTOS presentes por mes
    _parse_actual_report   — pipeline completo + flags `days_covered` / `partial`
    _actual_series         — {x, y, partial} con bridge al último histórico anterior
    _get_actual            — gemelo de _get_historical / _get_forecast

`partial` es TRI-ESTADO (`Optional[bool]`):
    True  → cobertura conocida e incompleta (BR diario, faltan días del mes)
    False → cobertura conocida y completa   (BR diario, mes cerrado)
    None  → cobertura DESCONOCIDA           (BR mensual: 1 fila ya agregada)

El caso `None` NO se resuelve acá: el helper es PURO (no llama `date.today()`).
Lo desambigua la UI en A3 comparando el mes de la fila contra hoy. Marcar `True`
a ciegas pintaría un mes CERRADO bajado en By Month como parcial en el evolutivo
— dato engañoso hacia el cliente.
"""

from __future__ import annotations

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Mini-CSVs sintéticos (inline) — mismos formatos reales que el resto de la suite
# ─────────────────────────────────────────────────────────────────────────────

# Julio 2026 tiene 31 días. Acá vienen 3 → mes PARCIAL, cobertura conocida.
_SYNTH_JULIO_PARCIAL = """\
Date,Ordered Product Sales,Ordered Product Sales - B2B,Units Ordered,Units Ordered - B2B,Sessions - Total,Sessions - Total - B2B,Page Views - Total,Featured Offer (Buy Box) Percentage,Order Item Session Percentage
7/1/26,"$1,234.56",$0.00,20,0,216,1,300,98.50%,9.26%
7/2/26,"$2,000.00",$10.00,19,0,234,4,320,97.00%,8.12%
7/3/26,"$3,000.00",$0.00,30,1,225,1,310,99.00%,13.33%
"""

# Junio 2026 tiene 30 días → CSV con los 30 → mes CERRADO, cobertura conocida.
_SYNTH_JUNIO_COMPLETO = "".join(
    ["Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage\n"]
    + [f"6/{d}/26,$100.00,2,50,4.00%\n" for d in range(1, 31)]
)

# Mixto: junio COMPLETO (30 días) + julio PARCIAL (3 días).
_SYNTH_MIXTO = "".join(
    ["Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage\n"]
    + [f"6/{d}/26,$100.00,2,50,4.00%\n" for d in range(1, 31)]
    + [f"7/{d}/26,$200.00,3,60,5.00%\n" for d in range(1, 4)]
)

# BR MENSUAL (By Month): 1 fila ya agregada por Amazon → cobertura DESCONOCIDA.
_SYNTH_MENSUAL = """\
Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage
2026-07-01,"$50,000.00",500,5000,10.00%
"""

# Sin columna Sessions → debe rechazar (heredado del parser existente).
_SYNTH_SESSIONLESS = """\
Date,Ordered Product Sales,Units Ordered,Shipped Product Sales
7/1/26,"$6,513.61",520,"$6,135.69"
"""


def _b(s: str) -> bytes:
    return s.encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# _read_br_rows — extract aditivo: granularidad ORIGINAL, sin agregar
# ─────────────────────────────────────────────────────────────────────────────

def test_read_br_rows_devuelve_granularidad_diaria_intacta():
    """El extract NO agrega: 3 filas diarias entran, 3 filas diarias salen.

    Es la razón de ser del extract — `_parse_actual_report` necesita contar
    días ANTES de que la agregación los colapse a 1 fila mensual.
    """
    rows = rf._read_br_rows(_b(_SYNTH_JULIO_PARCIAL), "julio.csv")
    assert len(rows) == 3
    assert [r["date"] for r in rows] == ["2026-07-01", "2026-07-02", "2026-07-03"]


def test_read_br_rows_ordena_asc_y_rechaza_sin_sessions():
    """Contrato heredado: orden asc por date + guard de reporte sin tráfico."""
    desordenado = (
        "Date,Ordered Product Sales,Units Ordered,Sessions - Total,Order Item Session Percentage\n"
        "7/3/26,$300.00,3,30,10.00%\n"
        "7/1/26,$100.00,1,10,10.00%\n"
    )
    rows = rf._read_br_rows(_b(desordenado), "d.csv")
    assert [r["date"] for r in rows] == ["2026-07-01", "2026-07-03"]

    with pytest.raises(rf.ReportLacksSessionsError):
        rf._read_br_rows(_b(_SYNTH_SESSIONLESS), "sessionless.csv")


def test_parse_business_report_sigue_dando_mensual_tras_el_extract():
    """Guard de no-regresión del extract: `_parse_business_report` conserva su
    contrato (agrega día→mes) aunque por dentro delegue en `_read_br_rows`.
    """
    out = rf._parse_business_report.__wrapped__(_b(_SYNTH_JULIO_PARCIAL), "julio.csv")
    assert len(out) == 1
    assert out[0]["date"] == "2026-07-01"
    assert out[0]["revenue"] == pytest.approx(1234.56 + 2000.00 + 3000.00, rel=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# _count_days_by_month
# ─────────────────────────────────────────────────────────────────────────────

def test_count_days_by_month_cuenta_dias_del_mes():
    rows = [{"date": f"2026-07-{d:02d}"} for d in range(1, 21)]
    assert rf._count_days_by_month(rows) == {"2026-07-01": 20}


def test_count_days_by_month_multi_mes():
    rows = (
        [{"date": f"2026-06-{d:02d}"} for d in range(1, 31)]
        + [{"date": f"2026-07-{d:02d}"} for d in range(1, 4)]
    )
    assert rf._count_days_by_month(rows) == {"2026-06-01": 30, "2026-07-01": 3}


def test_count_days_by_month_fechas_duplicadas_cuentan_una_vez():
    """Días DISTINTOS. Dos filas del mismo día no inflan la cobertura."""
    rows = [{"date": "2026-07-01"}, {"date": "2026-07-01"}, {"date": "2026-07-02"}]
    assert rf._count_days_by_month(rows) == {"2026-07-01": 2}


def test_count_days_by_month_saltea_date_malformado():
    """Mismo guard defensivo que `_detect_granularity`: filas rotas se ignoran."""
    rows = [{"date": "2026-07-01"}, {"date": "roto"}, {"date": None}, {}]
    assert rf._count_days_by_month(rows) == {"2026-07-01": 1}


# ─────────────────────────────────────────────────────────────────────────────
# _parse_actual_report — los TRES estados de `partial`
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_actual_report_mes_parcial_conocido():
    """Julio con 3 de 31 días → partial=True, days_covered=3."""
    out = rf._parse_actual_report(_b(_SYNTH_JULIO_PARCIAL), "julio.csv")
    assert len(out) == 1
    assert out[0]["date"] == "2026-07-01"
    assert out[0]["days_covered"] == 3
    assert out[0]["partial"] is True


def test_parse_actual_report_mes_completo_conocido():
    """Junio con los 30 días → partial=False (mes cerrado, cobertura completa)."""
    out = rf._parse_actual_report(_b(_SYNTH_JUNIO_COMPLETO), "junio.csv")
    assert len(out) == 1
    assert out[0]["days_covered"] == 30
    assert out[0]["partial"] is False


def test_parse_actual_report_mensual_cobertura_desconocida():
    """BR By Month (1 fila ya agregada) → NO se puede saber la cobertura.

    partial=None, NO True. Marcar True a ciegas pintaría un mes cerrado como
    parcial. La desambiguación es de A3 (comparar contra hoy).
    """
    out = rf._parse_actual_report(_b(_SYNTH_MENSUAL), "mensual.csv")
    assert len(out) == 1
    assert out[0]["date"] == "2026-07-01"
    assert out[0]["days_covered"] is None
    assert out[0]["partial"] is None


def test_parse_actual_report_documenta_los_tres_estados():
    """Los 3 estados de `partial` conviven en el módulo — test-documentación."""
    parcial = rf._parse_actual_report(_b(_SYNTH_JULIO_PARCIAL), "j.csv")[0]
    completo = rf._parse_actual_report(_b(_SYNTH_JUNIO_COMPLETO), "n.csv")[0]
    desconocido = rf._parse_actual_report(_b(_SYNTH_MENSUAL), "m.csv")[0]

    assert (parcial["partial"], completo["partial"], desconocido["partial"]) == (
        True, False, None,
    )
    # `partial` nunca es un bool "inventado" cuando days_covered es None.
    assert desconocido["days_covered"] is None


def test_parse_actual_report_multi_mes_resuelve_cada_mes_por_separado():
    """Junio cerrado + julio corriendo en el MISMO archivo → flags distintos.

    Es lo que hace que la capa sea EVOLUTIVA y no sólo "mes en curso".
    """
    out = rf._parse_actual_report(_b(_SYNTH_MIXTO), "mixto.csv")
    assert len(out) == 2
    assert out[0]["date"] == "2026-06-01"
    assert out[0]["partial"] is False
    assert out[0]["days_covered"] == 30
    assert out[1]["date"] == "2026-07-01"
    assert out[1]["partial"] is True
    assert out[1]["days_covered"] == 3


def test_parse_actual_report_shape_identico_al_de_historical():
    """🔴 Guard anti-bug clase-ventasPPC: si al parser de `actual` le faltara un
    campo, ese campo daría None silencioso en algún accessor de `_METRICS`.

    Contrato: sobre los MISMOS bytes, `_parse_actual_report` produce EXACTAMENTE
    las mismas keys que `_parse_business_report` (el que alimenta `historical`),
    más las 2 de la capa `actual`.
    """
    data = _b(_SYNTH_JULIO_PARCIAL)
    hist_row = rf._parse_business_report.__wrapped__(data, "x.csv")[0]
    actual_row = rf._parse_actual_report(data, "x.csv")[0]

    assert set(actual_row) - {"partial", "days_covered"} == set(hist_row)
    # Y los valores de los campos compartidos coinciden (mismo pipeline).
    for k in hist_row:
        assert actual_row[k] == hist_row[k], f"campo divergente: {k}"


def test_parse_actual_report_mapea_revenue_b2b():
    """`revenueB2B` (Ordered Product Sales - B2B) explícitamente presente."""
    out = rf._parse_actual_report(_b(_SYNTH_JULIO_PARCIAL), "julio.csv")
    assert "revenueB2B" in out[0]
    assert out[0]["revenueB2B"] == pytest.approx(10.00, rel=1e-6)


def test_parse_actual_report_limpia_moneda_y_fechas_us():
    """Hereda del parser existente: '$1,234.56', 'M/D/YY', '9.26%'."""
    out = rf._parse_actual_report(_b(_SYNTH_JULIO_PARCIAL), "julio.csv")
    assert out[0]["revenue"] == pytest.approx(1234.56 + 2000.00 + 3000.00, rel=1e-6)
    assert out[0]["sessions"] == 216 + 234 + 225
    assert out[0]["units"] == 20 + 19 + 30      # excluye B2B


def test_parse_actual_report_rechaza_reporte_sin_sessions():
    """Guard heredado: el reporte equivocado se rechaza, no se ingiere a medias."""
    with pytest.raises(rf.ReportLacksSessionsError):
        rf._parse_actual_report(_b(_SYNTH_SESSIONLESS), "sessionless.csv")


# ─────────────────────────────────────────────────────────────────────────────
# _actual_series — la 3ª serie, con bridge y flags alineados
# ─────────────────────────────────────────────────────────────────────────────

_ACC = rf._METRICS["revenue"]["from_hist"]


def _hist(*pairs):
    return [{"date": d, "revenue": v} for d, v in pairs]


def _actual(*triples):
    return [{"date": d, "revenue": v, "partial": p} for d, v, p in triples]


def test_actual_series_bridge_desde_ultimo_historico():
    """La serie `actual` ARRANCA repitiendo el último punto histórico — igual
    que la de forecast. Así ambas líneas salen del mismo lugar y divergen.
    """
    hist = _hist(("2026-05-01", 100.0), ("2026-06-01", 200.0))
    act = _actual(("2026-07-01", 300.0, True))

    s = rf._actual_series(hist, act, _ACC)
    assert s["x"] == ["2026-06-01", "2026-07-01"]
    assert s["y"] == [200.0, 300.0]


def test_actual_series_partial_alineado_con_bridge_false():
    """`partial` tiene la MISMA longitud que x/y. El punto de bridge es un punto
    HISTÓRICO (mes cerrado) → False, nunca None ni True.
    """
    hist = _hist(("2026-06-01", 200.0))
    act = _actual(("2026-07-01", 300.0, True), ("2026-08-01", 400.0, None))

    s = rf._actual_series(hist, act, _ACC)
    assert len(s["partial"]) == len(s["x"]) == len(s["y"]) == 3
    assert s["partial"] == [False, True, None]


def test_actual_series_sin_historico_no_hay_bridge():
    hist = []
    act = _actual(("2026-07-01", 300.0, True))

    s = rf._actual_series(hist, act, _ACC)
    assert s["x"] == ["2026-07-01"]
    assert s["y"] == [300.0]
    assert s["partial"] == [True]


def test_actual_series_sin_actual_devuelve_series_vacias():
    hist = _hist(("2026-06-01", 200.0))
    s = rf._actual_series(hist, [], _ACC)
    assert s == {"x": [], "y": [], "partial": []}


def test_actual_series_ancla_al_ultimo_historico_ESTRICTAMENTE_anterior():
    """🔴 Caso overlap: cuando un mes de `actual` CIERRA, entra también a
    `historical` — y ahí `hist[-1]` cae DENTRO del rango de actual, lo que haría
    que la línea vaya para atrás.

    El ancla es el último histórico estrictamente ANTERIOR al primer actual.
    """
    hist = _hist(("2026-05-01", 100.0), ("2026-06-01", 200.0), ("2026-07-01", 999.0))
    act = _actual(("2026-07-01", 300.0, True), ("2026-08-01", 400.0, True))

    s = rf._actual_series(hist, act, _ACC)
    assert s["x"] == ["2026-06-01", "2026-07-01", "2026-08-01"]
    assert s["y"] == [200.0, 300.0, 400.0]
    assert s["partial"] == [False, True, True]


def test_actual_series_sin_historico_anterior_no_bridgea():
    """Todo el histórico es POSTERIOR al primer actual → sin ancla, sin bridge."""
    hist = _hist(("2026-09-01", 100.0))
    act = _actual(("2026-07-01", 300.0, True))

    s = rf._actual_series(hist, act, _ACC)
    assert s["x"] == ["2026-07-01"]
    assert s["partial"] == [True]


def test_actual_series_bridge_copia_none_sin_inventar_valor():
    """Si el último histórico anterior no tiene valor para esa métrica, el bridge
    copia None (hueco en el chart) — NO inventa un 0.
    """
    hist = [{"date": "2026-06-01", "revenue": None}]
    act = _actual(("2026-07-01", 300.0, True))

    s = rf._actual_series(hist, act, _ACC)
    assert s["y"] == [None, 300.0]
    assert s["partial"] == [False, True]


def test_actual_series_funciona_con_las_10_metricas_del_catalogo():
    """Las filas de `actual` tienen shape de `historical` → los 10 accessors
    `from_hist` funcionan tal cual. Cero accessors nuevos en A1.
    """
    hist = [{"date": "2026-06-01", "revenue": 200.0, "units": 10, "sessions": 100,
             "cvr": 10.0, "spend": 50.0, "ventasPPC": 150.0}]
    act = [{"date": "2026-07-01", "revenue": 300.0, "units": 15, "sessions": 120,
            "cvr": 12.5, "spend": 60.0, "ventasPPC": 180.0, "partial": True}]

    for mid, m in rf._METRICS.items():
        s = rf._actual_series(hist, act, m["from_hist"])
        assert len(s["x"]) == len(s["y"]) == len(s["partial"]) == 2, f"métrica {mid}"


def test_bridge_sigue_devolviendo_dos_series():
    """Guard de no-regresión: A1 NO toca `_bridge`. Su arity sigue siendo 2."""
    hist = _hist(("2026-06-01", 200.0))
    fc = [{"date": "2026-07-01", "revenue": 300.0}]
    out = rf._bridge(hist, fc, _ACC, rf._METRICS["revenue"]["from_fc"])
    assert isinstance(out, tuple) and len(out) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Merge y estado
# ─────────────────────────────────────────────────────────────────────────────

def test_merge_historical_propaga_flags_de_actual():
    """La capa `actual` REUSA `_merge_historical` (no necesita gemelo): match por
    date, orden asc, counts, y propaga `partial`/`days_covered` sin tocarlo.
    """
    existing = [{"date": "2026-06-01", "revenue": 100.0, "partial": False,
                 "days_covered": 30, "spend": None, "ventasPPC": None}]
    incoming = [
        {"date": "2026-06-01", "revenue": 111.0, "partial": False, "days_covered": 30},
        {"date": "2026-07-01", "revenue": 222.0, "partial": True, "days_covered": 3},
    ]
    merged, added, updated = rf._merge_historical(existing, incoming)

    assert (added, updated) == (1, 1)
    assert [r["date"] for r in merged] == ["2026-06-01", "2026-07-01"]
    assert merged[1]["partial"] is True
    assert merged[1]["days_covered"] == 3


def test_merge_historical_preserva_spend_cargado_a_mano():
    """El BR no trae spend/ventasPPC: lo que cargó el AM no se pisa al re-subir."""
    existing = [{"date": "2026-07-01", "revenue": 100.0, "spend": 42.0,
                 "ventasPPC": 84.0, "partial": True, "days_covered": 3}]
    incoming = [{"date": "2026-07-01", "revenue": 150.0, "partial": True, "days_covered": 5}]

    merged, _added, _updated = rf._merge_historical(existing, incoming)
    assert merged[0]["spend"] == 42.0
    assert merged[0]["ventasPPC"] == 84.0
    assert merged[0]["revenue"] == 150.0
    assert merged[0]["days_covered"] == 5


def test_new_client_incluye_actual_vacio():
    c = rf._new_client(name="Test", client_id="t1")
    assert c["actual"] == []


def test_get_actual_sin_cliente_activo_devuelve_lista_vacia():
    state = {}
    rf._ensure_state(state=state)
    assert rf._get_actual(state=state) == []


def test_get_actual_tolera_cliente_viejo_sin_la_key():
    """Retrocompatibilidad: clientes hidratados de Supabase ANTES de F7-A no
    tienen la key `actual`. El getter no debe romper.
    """
    viejo = rf._new_client(name="Viejo", client_id="viejo")
    del viejo["actual"]
    state = {}
    rf._ensure_state(state=state)
    state[rf._K_CLIENTS] = [viejo]
    state[rf._K_ACTIVE_CLIENT_ID] = "viejo"

    assert rf._get_actual(state=state) == []


def test_get_actual_devuelve_las_filas_del_cliente_activo():
    c = rf._new_client(name="Con Actual", client_id="con-actual")
    c["actual"] = [{"date": "2026-07-01", "revenue": 300.0, "partial": True}]
    state = {}
    rf._ensure_state(state=state)
    state[rf._K_CLIENTS] = [c]
    state[rf._K_ACTIVE_CLIENT_ID] = "con-actual"

    assert rf._get_actual(state=state) == c["actual"]

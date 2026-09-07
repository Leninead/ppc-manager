"""M31 F6 — Tests del forecast por-ASIN aplicado al EXPORT (Bloque 1).

Cubre la capa PURA que le da forecast a la sección "Detalle por ASIN" del
deliverable HTML: `_asin_forecast_for_export` (agregación del motor por ASIN a
nivel parent y cuenta) y el parámetro `forecast` de `_asin_table_html`.

Contexto del bug: el export mostraba sólo meses reales por ASIN mientras la capa
cuenta sí proyectaba, porque `_forecast_single_asin` sólo se disparaba desde la
UI y se cacheaba en session_state — el export nunca lo veía.

NO tocan Streamlit ni fixtures reales gitignored: todos los modelos son
sintéticos inline, para que la suite corra en una checkout limpia.
"""

from __future__ import annotations

import time

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de fixtures sintéticos
# ─────────────────────────────────────────────────────────────────────────────

_OPTS = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": False}


def _h(period: str, revenue: float, units: float = 10.0,
       sessions: float = 400.0, cvr: float = 2.5, partial: bool = False) -> dict:
    """Una entrada de `node["history"]` tal como la arma
    `_accumulate_asin_snapshots` (el CVR viaja como `unit_session_pct`).
    """
    entry = {"period": period, "revenue": revenue, "units": units,
             "sessions": sessions, "unit_session_pct": cvr}
    if partial:
        entry["partial"] = True
    return entry


def _node(parent: str, title: str, history: list) -> dict:
    return {"parent_asin": parent, "title": title, "history": history}


def _model_hero() -> dict:
    """1 ASIN con 2 meses completos — los números reales del caso reportado."""
    return {"B0GTW5ZL5K": _node("B0GTW5ZL5K", "Hero", [
        _h("2026-07", 458.0), _h("2026-08", 686.0)])}


# ─────────────────────────────────────────────────────────────────────────────
# _asin_forecast_for_export
# ─────────────────────────────────────────────────────────────────────────────

def test_export_fc_shape_vacio_sin_datos_suficientes():
    """1 solo mes → el motor no puede sacar MoM. Dict vacío canónico, no None."""
    model = {"B0AAA": _node("B0AAA", "Nuevo", [_h("2026-08", 100.0)])}
    out = rf._asin_forecast_for_export(model, _OPTS)
    assert out == {"periods": [], "parent": {}, "cuenta": {}}


def test_export_fc_dos_meses_completos_proyecta():
    out = rf._asin_forecast_for_export(_model_hero(), _OPTS)
    assert out["periods"] == ["2026-09", "2026-10", "2026-11"]
    assert set(out["parent"]) == {"B0GTW5ZL5K"}
    assert sorted(out["parent"]["B0GTW5ZL5K"]) == [
        "2026-09", "2026-10", "2026-11"]
    for p in out["periods"]:
        assert set(out["cuenta"][p]) == {"revenue", "units", "sessions"}
        assert out["cuenta"][p]["revenue"] > 0


def test_export_fc_periods_formato_yyyy_mm():
    """El motor devuelve 'YYYY-MM-01'; el export los necesita en 'YYYY-MM' para
    poder concatenarlos con los períodos reales del history en una sola fila.
    """
    out = rf._asin_forecast_for_export(_model_hero(), _OPTS)
    assert out["periods"]
    for p in out["periods"]:
        assert len(p) == 7 and not p.endswith("-01")
    for par_map in out["parent"].values():
        for p in par_map:
            assert len(p) == 7 and not p.endswith("-01")
    for p in out["cuenta"]:
        assert len(p) == 7 and not p.endswith("-01")


def test_export_fc_asin_insuficiente_no_rompe_a_los_demas():
    """3 de 40 ASINs nuevos no pueden dejar sin export a los otros 37."""
    model = {
        "B0OK": _node("B0OK", "Con historia",
                      [_h("2026-07", 458.0), _h("2026-08", 686.0)]),
        "B0NEW": _node("B0NEW", "Recién lanzado", [_h("2026-08", 50.0)]),
    }
    out = rf._asin_forecast_for_export(model, _OPTS)
    assert out["periods"]
    assert "B0OK" in out["parent"]
    assert "B0NEW" not in out["parent"]


def test_export_fc_parent_suma_childs():
    """El revenue del parent en cada período == suma de sus childs. El esperado
    se DERIVA llamando al motor por separado, nunca hardcodeado.
    """
    ch_a = [_h("2026-07", 458.0), _h("2026-08", 686.0)]
    ch_b = [_h("2026-07", 200.0), _h("2026-08", 240.0)]
    model = {
        "B0CH1": _node("B0PAR", "Child 1", ch_a),
        "B0CH2": _node("B0PAR", "Child 2", ch_b),
    }
    out = rf._asin_forecast_for_export(model, _OPTS)

    esperado: dict = {}
    for fc in (rf._forecast_single_asin(ch_a, _OPTS),
               rf._forecast_single_asin(ch_b, _OPTS)):
        assert fc, "ambos childs tienen 2 meses completos: deben proyectar"
        for r in fc:
            p = r["date"][:7]
            esperado[p] = esperado.get(p, 0.0) + rf._js_number(r.get("revenue"))

    assert set(out["parent"]) == {"B0PAR"}
    assert sorted(out["parent"]["B0PAR"]) == sorted(esperado)
    for p, v in esperado.items():
        assert out["parent"]["B0PAR"][p] == v


def test_export_fc_performance_60_asins():
    """Canario anti-regresión de complejidad, no un benchmark: el umbral es
    holgado a propósito. Si alguien mete un for anidado sobre el modelo, salta.
    """
    model = {
        f"B0{i:04d}": _node(f"B0PAR{i % 7}", f"ASIN {i}", [
            _h("2026-06", 300.0 + i), _h("2026-07", 400.0 + i),
            _h("2026-08", 500.0 + i)])
        for i in range(60)
    }
    t0 = time.perf_counter()
    out = rf._asin_forecast_for_export(model, _OPTS)
    elapsed = time.perf_counter() - t0
    assert out["periods"], "los 60 ASINs tienen 3 meses completos: deben proyectar"
    assert elapsed < 5.0, f"tardó {elapsed:.2f}s (umbral 5s)"


# ─────────────────────────────────────────────────────────────────────────────
# _asin_table_html — parámetro forecast
# ─────────────────────────────────────────────────────────────────────────────

def test_asin_table_html_sin_forecast_es_identico():
    """LOAD-BEARING: con forecast=None el output tiene que ser byte-idéntico al
    del default, así ningún caller existente cambia de comportamiento.
    """
    model = _model_hero()
    for level in ("parent", "cuenta"):
        base = rf._asin_table_html(model, level, "USD")
        con_none = rf._asin_table_html(model, level, "USD", forecast=None)
        assert base == con_none
        assert "(fc)" not in base


def test_asin_table_html_parent_agrega_columnas_fc():
    model = _model_hero()
    fc = rf._asin_forecast_for_export(model, _OPTS)
    html_out = rf._asin_table_html(model, "parent", "USD", forecast=fc)
    assert "2026-09 (fc)" in html_out
    esperado = rf._fmt_currency(fc["parent"]["B0GTW5ZL5K"]["2026-09"], "USD")
    assert esperado in html_out
    # Los períodos reales siguen estando.
    assert "2026-07" in html_out and "2026-08" in html_out


def test_asin_table_html_cuenta_agrega_filas_fc():
    model = _model_hero()
    fc = rf._asin_forecast_for_export(model, _OPTS)
    html_out = rf._asin_table_html(model, "cuenta", "USD", forecast=fc)
    assert "2026-09 (fc)" in html_out
    assert "2026-10 (fc)" in html_out
    # Las filas reales no se pisan.
    assert ">2026-07<" in html_out and ">2026-08<" in html_out


def test_asin_table_html_child_ignora_forecast():
    """El nivel child no lleva forecast al export (E7): el param se ignora sin
    error y no marca nada.
    """
    model = _model_hero()
    fc = rf._asin_forecast_for_export(model, _OPTS)
    html_out = rf._asin_table_html(model, "child", "USD", forecast=fc)
    assert html_out
    assert "(fc)" not in html_out


def test_export_fc_label_periodo_aclara_asins_cargados():
    """El header decía "Período" a secas y se leía como el total de la cuenta;
    son los ASINs que el AM cargó.
    """
    html_out = rf._asin_table_html(_model_hero(), "cuenta", "USD")
    assert "Período (ASINs cargados)" in html_out

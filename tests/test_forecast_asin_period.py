"""Tests del importer By ASIN: inferencia de período + real-vs-forecast.

Dos piezas:

    1. `_infer_asin_period` — el bug que hacía ver el importer como "roto". El
       export real de Amazon se llama `BusinessReport-8-04-26.csv` y NO contiene
       `20\\d\\d`, así que el regex ISO nunca matcheaba: el importer caía siempre
       al input manual y, sin completarlo con el formato exacto, cortaba con un
       warning antes de parsear nada.

    2. `_asin_realvs_forecast_series` — las series real + forecast de UN ASIN.
       RESTRICCIÓN DURA blindada acá: el reporte By Child Item no trae spend ni
       ventas PPC, así que ACOS / TACOS / Spend / Ventas PPC NO se pueden pedir
       por ASIN. Pedirlas tiene que fallar fuerte, no devolver un chart vacío.
"""

from __future__ import annotations

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# 1. _infer_asin_period
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename,esperado", [
    # Naming REAL de Amazon: BusinessReport-M-DD-YY (el caso que estaba roto).
    ("BusinessReport-8-04-26.csv", "2026-08"),
    ("BusinessReport-12-31-25.csv", "2025-12"),
    ("BusinessReport-1-01-26.csv", "2026-01"),
    # Descarga duplicada del browser — el sufijo " (2)" no molesta.
    ("BusinessReport-7-10-26 (2).csv", "2026-07"),
    # Naming ISO que el importer ya soportaba (archivo renombrado por el AM).
    ("dermaglos_2026-07.csv", "2026-07"),
])
def test_infer_asin_period_formatos_soportados(filename, esperado):
    assert rf._infer_asin_period(filename) == esperado


def test_infer_asin_period_sin_fecha_devuelve_none():
    """Sin fecha reconocible → None, y el caller cae al input manual."""
    assert rf._infer_asin_period("reporte_final.csv") is None
    assert rf._infer_asin_period("BusinessReport.csv") is None
    assert rf._infer_asin_period("") is None
    assert rf._infer_asin_period(None) is None


def test_infer_asin_period_mes_invalido_devuelve_none():
    """Mes fuera de 1-12 no se adivina — cae al input manual."""
    assert rf._infer_asin_period("BusinessReport-13-04-26.csv") is None
    assert rf._infer_asin_period("BusinessReport-0-04-26.csv") is None


def test_infer_asin_period_iso_gana_sobre_amazon():
    """Si el nombre trae YYYY-MM, ese manda (es explícito del AM)."""
    assert rf._infer_asin_period("BusinessReport-2026-07.csv") == "2026-07"


def test_infer_asin_period_no_confunde_ano_de_4_digitos():
    """`-2026` como año NO se lee como `20` → 2020 (guard del lookahead)."""
    # Acá gana el ISO igual, pero el guard importa si el ISO no matcheara.
    assert rf._infer_asin_period("BusinessReport-8-04-2026.csv") != "2020-08"


def test_infer_asin_period_case_insensitive():
    assert rf._infer_asin_period("businessreport-8-04-26.csv") == "2026-08"
    assert rf._infer_asin_period("BUSINESSREPORT-8-04-26.CSV") == "2026-08"


# ─────────────────────────────────────────────────────────────────────────────
# 2. _asin_realvs_forecast_series
# ─────────────────────────────────────────────────────────────────────────────

def _history() -> list[dict]:
    """History de un ASIN: 3 meses, el último parcial."""
    return [
        {"period": "2026-05", "sessions": 100.0, "page_views": 150.0,
         "buy_box_pct": 95.0, "units": 10.0, "unit_session_pct": 10.0,
         "revenue": 500.0},
        {"period": "2026-06", "sessions": 120.0, "page_views": 180.0,
         "buy_box_pct": 96.0, "units": 14.0, "unit_session_pct": 11.7,
         "revenue": 700.0},
        {"period": "2026-07", "sessions": 60.0, "page_views": 90.0,
         "buy_box_pct": 96.0, "units": 7.0, "unit_session_pct": 11.7,
         "revenue": 350.0, "partial": True, "days_covered": 15},
    ]


_OPTS = {"horizon": 2, "momWindow": 3, "blend": 50, "useSeasonality": False}


@pytest.mark.parametrize("metric_id", ["revenue", "sessions", "units", "cvr"])
def test_series_arma_real_y_forecast_para_las_4_metricas(metric_id):
    """Las 4 métricas permitidas devuelven real + forecast con bridge."""
    hist = _history()
    fc = rf._forecast_single_asin(hist, _OPTS)
    assert fc, "el fixture tiene 2 meses completos — el forecast no puede salir vacío"

    s = rf._asin_realvs_forecast_series(hist, fc, metric_id)

    # Real: un punto por mes cargado (incluido el parcial), en fecha ISO.
    assert s["real"]["x"] == ["2026-05-01", "2026-06-01", "2026-07-01"]
    assert len(s["real"]["y"]) == 3
    assert all(v is not None for v in s["real"]["y"])

    # Partial alineado: sólo el último mes está en curso.
    assert s["real"]["partial"] == [False, False, True]

    # Forecast: bridge desde el último punto real → las líneas se tocan.
    assert len(s["forecast"]["x"]) == len(fc) + 1
    assert s["forecast"]["x"][0] == s["real"]["x"][-1]
    assert s["forecast"]["y"][0] == s["real"]["y"][-1]


def test_series_cvr_lee_unit_session_pct_del_history():
    """El mapeo de nombres del history (unit_session_pct → cvr) se respeta."""
    hist = _history()
    fc = rf._forecast_single_asin(hist, _OPTS)
    s = rf._asin_realvs_forecast_series(hist, fc, "cvr")
    assert s["real"]["y"] == [10.0, 11.7, 11.7]


def test_series_sin_forecast_devuelve_solo_real():
    """Sin forecast (menos de 2 meses completos) el real igual se grafica."""
    hist = _history()[:1]
    s = rf._asin_realvs_forecast_series(hist, [], "revenue")
    assert s["real"]["x"] == ["2026-05-01"]
    assert s["forecast"]["x"] == []
    assert s["forecast"]["y"] == []


def test_series_history_vacio_no_rompe():
    s = rf._asin_realvs_forecast_series([], [], "revenue")
    assert s["real"]["x"] == []
    assert s["forecast"]["x"] == []


@pytest.mark.parametrize("metric_id", ["acos", "tacos", "spend", "ventasPPC"])
def test_series_rechaza_metricas_de_ads(metric_id):
    """🔴 El reporte By ASIN no trae inversión de Ads — pedirla tiene que fallar.

    Devolver una serie vacía sería peor: un chart en blanco se lee como "este
    ASIN no tiene datos" en vez de "esta métrica no existe a este nivel".
    """
    hist = _history()
    with pytest.raises(ValueError) as exc:
        rf._asin_realvs_forecast_series(hist, [], metric_id)
    assert metric_id in str(exc.value)


def test_catalogo_de_metricas_por_asin_es_exactamente_las_4():
    """Blindaje del contrato: nadie suma acos/spend al selector sin romper esto."""
    assert rf._ASIN_CHART_METRICS == ("revenue", "sessions", "units", "cvr")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Chart (ensamblado — sin Streamlit)
# ─────────────────────────────────────────────────────────────────────────────

def test_chart_arma_dos_traces_real_y_forecast():
    hist = _history()
    fc = rf._forecast_single_asin(hist, _OPTS)
    fig = rf._asin_realvs_forecast_chart(hist, fc, "revenue")

    assert len(fig.data) == 2
    assert fig.data[0].name == "Revenue (real)"
    assert fig.data[1].name == "Revenue (forecast)"
    # El forecast va dashed; el real, sólido.
    assert fig.data[1].line.dash == "dash"
    assert fig.data[0].line.dash is None


def test_chart_marca_el_mes_parcial_con_punto_hueco():
    hist = _history()
    fig = rf._asin_realvs_forecast_chart(hist, [], "revenue")
    symbols = list(fig.data[0].marker.symbol)
    assert symbols == ["circle", "circle", "circle-open"]
    assert list(fig.data[0].marker.size)[-1] == rf._MARKER_SIZE_PARTIAL


def test_chart_sin_history_devuelve_figura_vacia():
    fig = rf._asin_realvs_forecast_chart([], [], "revenue")
    assert len(fig.data) == 0

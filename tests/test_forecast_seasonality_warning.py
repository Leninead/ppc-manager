"""M31 — warning de estacionalidad distorsionada (Opción 3, 2026-09-22).

El bug: `auto_detect_seasonality` promedia cada mes-del-año sobre todos los años SIN
quitar la tendencia. Con crecimiento YoY fuerte, un mes que todavía no tiene dato del
año en curso solo promedia años viejos (más bajos) y su índice queda bajo; el forecast
de ese mes sale subestimado.

Hoy NO se toca el cálculo (ni `auto_detect_seasonality` ni `generate_forecast`): solo
se detecta la condición y se avisa en la UI. Todos los datos acá son SINTÉTICOS: un
negocio plano dentro de cada año (sin estacionalidad real) que crece de un año a otro,
así que cualquier índice distinto de 1.00 es el bug y no estacionalidad.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from modules.pages import revenue_forecast as rf

_OPTS = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": True}


def _hist(desde: str, hasta: str, nivel_por_anio: dict[int, float]) -> list[dict]:
    """Historial mensual [desde, hasta] ('YYYY-MM'), revenue plano por año."""
    y, m = map(int, desde.split("-"))
    y_fin, m_fin = map(int, hasta.split("-"))
    rows = []
    while (y, m) <= (y_fin, m_fin):
        rev = nivel_por_anio[y]
        rows.append({
            "date": f"{y}-{m:02d}-01", "revenue": rev, "units": rev / 50,
            "sessions": rev / 5, "cvr": 10, "buyBox": 95, "pageViews": rev / 3,
            "revenueB2B": 0, "spend": None, "ventasPPC": None,
        })
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return rows


def _forecast(hist: list[dict], use_season: bool = True) -> list[dict]:
    """Forecast real del motor (sin tocarlo), con los índices auto-detectados."""
    seasonality = rf.auto_detect_seasonality(hist)
    opts = {**_OPTS, "useSeasonality": use_season}
    return rf.generate_forecast(opts, hist, seasonality, "auto")


# Goyo-like: ene-2025 a ago-2026 (20 meses), 2026 factura 2.2x que 2025 (+120% YoY).
_HIST_CRECE = _hist("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0})


# ---------------------------------------------------------------------------
# El mecanismo (documenta el bug; no se corrige hoy)
# ---------------------------------------------------------------------------

def test_mecanismo_meses_sin_dato_del_anio_quedan_con_indice_bajo():
    idx = rf.auto_detect_seasonality(_HIST_CRECE)["indices"]
    # Negocio plano: todos deberían ser 1.00. Ene-ago promedian 2025+2026 (alto),
    # sep-dic solo 2025 (bajo). Índice sep = 3 / (3 + 1.2) ≈ 0.714.
    assert idx[8] == pytest.approx(0.714, abs=0.001)            # septiembre
    assert all(i < 1 for i in idx[8:12])
    assert all(i > 1 for i in idx[0:8])


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------

def test_detecta_crecimiento_fuerte_con_meses_sin_dato_del_anio():
    riesgo = rf._detectar_riesgo_estacionalidad(_HIST_CRECE, _forecast(_HIST_CRECE))

    assert riesgo is not None
    assert riesgo["anio"] == 2026
    assert riesgo["meses"] == ["Septiembre", "Octubre", "Noviembre"]
    assert riesgo["yoy"] == pytest.approx(1.2)


def test_no_detecta_con_poco_crecimiento():
    hist = _hist("2025-01", "2026-08", {2025: 10_000.0, 2026: 11_000.0})  # +10%
    assert rf._detectar_riesgo_estacionalidad(hist, _forecast(hist)) is None


def test_no_detecta_con_historia_completa_del_anio():
    # Último dato dic-2026: el forecast (ene-mar 2027) cae en meses que SÍ tienen
    # dato del año en curso, así que todos los índices mezclan los mismos años.
    hist = _hist("2025-01", "2026-12", {2025: 10_000.0, 2026: 22_000.0})
    assert rf._detectar_riesgo_estacionalidad(hist, _forecast(hist)) is None


def test_no_detecta_si_el_forecast_no_aplico_estacionalidad():
    fc = _forecast(_HIST_CRECE, use_season=False)
    assert rf._detectar_riesgo_estacionalidad(_HIST_CRECE, fc) is None


def test_no_detecta_sin_meses_para_comparar_contra_el_anio_anterior():
    # 12 meses (sep-2025 a ago-2026): ningún mes tiene su par del año anterior.
    hist = _hist("2025-09", "2026-08", {2025: 10_000.0, 2026: 22_000.0})
    fc = [{"date": "2026-09-01", "month": 8, "seasonality": 0.7}]
    assert rf._detectar_riesgo_estacionalidad(hist, fc) is None


def test_umbral_de_crecimiento():
    justo = _hist("2025-01", "2026-08", {2025: 10_000.0, 2026: 15_000.0})    # +50%
    arriba = _hist("2025-01", "2026-08", {2025: 10_000.0, 2026: 15_100.0})   # +51%

    assert rf._detectar_riesgo_estacionalidad(justo, _forecast(justo)) is None
    assert rf._detectar_riesgo_estacionalidad(arriba, _forecast(arriba)) is not None


def test_sin_historial_o_sin_forecast_no_detecta():
    assert rf._detectar_riesgo_estacionalidad([], _forecast(_HIST_CRECE)) is None
    assert rf._detectar_riesgo_estacionalidad(_HIST_CRECE, []) is None


# ---------------------------------------------------------------------------
# Mensaje
# ---------------------------------------------------------------------------

def test_mensaje_nombra_los_meses_y_sugiere_que_hacer():
    msg = rf._mensaje_riesgo_estacionalidad(
        {"anio": 2026, "meses": ["Septiembre", "Octubre", "Noviembre"], "yoy": 1.2})

    assert "Septiembre, Octubre y Noviembre no tienen datos de 2026" in msg
    assert "+120%" in msg
    assert "destildar" in msg and "override manual" in msg


def test_mensaje_en_singular_con_un_solo_mes():
    msg = rf._mensaje_riesgo_estacionalidad(
        {"anio": 2026, "meses": ["Diciembre"], "yoy": 0.8})
    assert "Diciembre no tiene datos de 2026" in msg


# ---------------------------------------------------------------------------
# UI — el warning aparece en la sección Forecast
# ---------------------------------------------------------------------------

_REPO_ROOT = str(Path(__file__).resolve().parents[1])

_SECTION_APP = """
import sys
sys.path.insert(0, r"__REPO_ROOT__")
import streamlit as st
from modules.pages import revenue_forecast as rf
from tests.test_forecast_seasonality_warning import _hist, _forecast

hist = _hist("2025-01", "2026-08", {2025: 10_000.0, 2026: __NIVEL_2026__})
c = rf._new_client(name="T", client_id="t1")
c["historical"] = hist
c["seasonality"] = rf.auto_detect_seasonality(hist)
c["forecast"] = _forecast(hist)
st.session_state[rf._K_CLIENTS] = [c]
st.session_state[rf._K_ACTIVE_CLIENT_ID] = "t1"
st.session_state[rf._K_ACCOUNT_MANAGERS] = []

rf._render_forecast_section(c)
"""


def _run_section(nivel_2026: float) -> AppTest:
    script = (_SECTION_APP.replace("__REPO_ROOT__", _REPO_ROOT)
              .replace("__NIVEL_2026__", repr(nivel_2026)))
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


def _warnings_estacionalidad(at: AppTest) -> list[str]:
    return [w.value for w in at.warning if "estacionalidad" in w.value.lower()]


def test_ui_muestra_el_warning_con_crecimiento_fuerte():
    at = _run_section(22_000.0)

    assert not at.exception
    [msg] = _warnings_estacionalidad(at)
    assert "Septiembre, Octubre y Noviembre" in msg


def test_ui_no_muestra_el_warning_en_un_caso_normal():
    at = _run_section(11_000.0)

    assert not at.exception
    assert _warnings_estacionalidad(at) == []

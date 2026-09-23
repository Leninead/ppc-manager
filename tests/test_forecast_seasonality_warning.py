"""M31 — warning de sobre-proyección por crecimiento YoY fuerte.

Un mes del forecast sin dato del año en curso se proyecta desde el mismo mes del año
anterior crecido al YoY reciente: si ese crecimiento no se sostiene, el forecast queda
inflado. El warning avisa, con o sin estacionalidad. Todos los datos acá son
SINTÉTICOS: un negocio plano dentro de cada año que crece de un año a otro.
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
# El crecimiento ya no se lee como estacionalidad
# ---------------------------------------------------------------------------

def test_los_meses_sin_dato_del_anio_ya_no_quedan_con_indice_bajo():
    # Antes del fix, septiembre salía 0.714 en este negocio plano.
    assert rf.auto_detect_seasonality(_HIST_CRECE)["indices"] == [1.0] * 12


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
    # dato del año en curso.
    hist = _hist("2025-01", "2026-12", {2025: 10_000.0, 2026: 22_000.0})
    assert rf._detectar_riesgo_estacionalidad(hist, _forecast(hist)) is None


def test_detecta_tambien_si_el_forecast_no_aplico_estacionalidad():
    fc = _forecast(_HIST_CRECE, use_season=False)
    riesgo = rf._detectar_riesgo_estacionalidad(_HIST_CRECE, fc)
    assert riesgo is not None
    assert riesgo["meses"] == ["Septiembre", "Octubre", "Noviembre"]


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

def test_mensaje_avisa_la_sobre_proyeccion_con_los_meses_y_el_crecimiento():
    msg = rf._mensaje_riesgo_estacionalidad(
        {"anio": 2026, "meses": ["Septiembre", "Octubre", "Noviembre"], "yoy": 1.48})

    assert msg == (
        "⚠️ Esta proyección puede quedar inflada. La cuenta viene creciendo +148% "
        "interanual en los últimos meses, y el forecast de Septiembre, Octubre y "
        "Noviembre supone que ese ritmo se sostiene sobre lo vendido en 2025. Si el "
        "crecimiento se frena, el número real va a quedar por debajo. Si el mes en "
        "curso ya tiene ventas, comparalas con la proyección antes de mandarla."
    )


def test_mensaje_con_un_solo_mes():
    msg = rf._mensaje_riesgo_estacionalidad(
        {"anio": 2026, "meses": ["Diciembre"], "yoy": 0.8})
    assert "el forecast de Diciembre supone" in msg


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
    return [w.value for w in at.warning if "inflada" in w.value.lower()]


def test_ui_muestra_el_warning_con_crecimiento_fuerte():
    at = _run_section(22_000.0)

    assert not at.exception
    [msg] = _warnings_estacionalidad(at)
    assert "Septiembre, Octubre y Noviembre" in msg


def test_ui_no_muestra_el_warning_en_un_caso_normal():
    at = _run_section(11_000.0)

    assert not at.exception
    assert _warnings_estacionalidad(at) == []

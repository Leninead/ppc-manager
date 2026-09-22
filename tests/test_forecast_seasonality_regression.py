"""M31 — ESQUELETO del test de regresión para el fix de fondo de estacionalidad.

Fix de fondo pendiente: Opción 1+4 (desestacionalizar + normalizar). NO está
implementado. Este archivo deja lista la red de seguridad para cuando llegue:

  A. Invariantes SINTÉTICOS — corren hoy, marcados `xfail(strict=True)`: fallan con el
     cálculo actual. Cuando el fix entre van a pasar, y `strict` hace fallar la suite
     (XPASS) para obligar a sacar el marcador. No hace falta ningún dato real.

  B. Histórico REAL por cuenta — se saltean hasta que estén los CSV. Formato:

         tests/fixtures/real/seasonality/<cuenta>_historico.csv   (gitignored)

         mes,revenue,units,sessions
         2025-01,10000.50,200,2000
         2025-02,...

     · `mes` = YYYY-MM, meses consecutivos sin huecos, orden ascendente.
     · Mínimo 20 meses (el bug necesita 1 año completo + meses del año en curso).
     · Revenue en la moneda del marketplace, sin símbolo ni separador de miles.

  C. Números esperados por cuenta — placeholders `None`: el AM dice qué proyección
     "cierra" para cada mes. Se saltean hasta completarlos.

Cuentas (TODO al llegar los datos):
  · goyo     — reportado por Gregorio Martino. Bug confirmado.
  · trafilea — reportado por Tatiana Velasquez. A CONFIRMAR si es el mismo mecanismo:
               el test `test_cuenta_real_presenta_el_patron_del_bug` es esa confirmación
               (si el aviso de la Opción 3 no se dispara con su histórico, es otro bug).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import pytest

from modules.pages import revenue_forecast as rf

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "real" / "seasonality"
_COLUMNAS = ["mes", "revenue", "units", "sessions"]
_MIN_MESES = 20

# Reason común: al sacar los xfail, buscar esta string.
_BUG = "Bug estacionalidad M31: índices sin desestacionalizar (fix Opción 1+4 pendiente)"


# ═══════════════════════════════════════════════════════════════════════════
# Configuración por cuenta — COMPLETAR cuando llegue el histórico real
# ═══════════════════════════════════════════════════════════════════════════

CUENTAS: dict[str, dict] = {
    "goyo": {
        "archivo": "goyo_historico.csv",
        # True = bug confirmado; None = a confirmar con el histórico.
        "mismo_bug": True,
        # TODO(goyo): opciones con las que el AM genera el forecast en la UI.
        "opts": {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": True},
        "yoy_mode": "auto",
        # TODO(goyo): proyección que "cierra" según el AM, por mes: {"2026-10": 123456.0}.
        "esperado": None,
        # Tolerancia relativa contra `esperado` (0.15 = ±15%).
        "tolerancia": 0.15,
    },
    "trafilea": {
        "archivo": "trafilea_historico.csv",
        "mismo_bug": None,  # TODO(trafilea): confirmar con Tatiana Velasquez.
        "opts": {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": True},
        "yoy_mode": "auto",
        "esperado": None,   # TODO(trafilea)
        "tolerancia": 0.15,
    },
}


def _cargar_historico(nombre_archivo: str) -> Optional[list[dict]]:
    """Lee el CSV real y lo convierte al formato de filas que usa el motor.

    Devuelve None si el archivo no está (gitignored: vive solo en la máquina local).
    Los campos que el CSV no trae van neutros: el bug es de revenue.
    """
    path = _FIXTURES / nombre_archivo
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != _COLUMNAS:
            raise AssertionError(
                f"{nombre_archivo}: columnas {reader.fieldnames}, se esperaban {_COLUMNAS}")
        rows = []
        for r in reader:
            units = float(r["units"])
            sessions = float(r["sessions"])
            rows.append({
                "date": f"{r['mes']}-01",
                "revenue": float(r["revenue"]),
                "units": units,
                "sessions": sessions,
                "cvr": (units / sessions * 100) if sessions else 0.0,
                "buyBox": None, "pageViews": 0, "revenueB2B": 0,
                "spend": None, "ventasPPC": None,
            })
    return rows


def _historico_o_skip(cuenta: str) -> list[dict]:
    rows = _cargar_historico(CUENTAS[cuenta]["archivo"])
    if rows is None:
        pytest.skip(f"TODO({cuenta}): falta tests/fixtures/real/seasonality/"
                    f"{CUENTAS[cuenta]['archivo']}")
    return rows


def _hist_sintetico(desde: str, hasta: str, nivel_por_anio: dict[int, float],
                    perfil: Optional[list[float]] = None) -> list[dict]:
    """Historial mensual sintético: nivel del año × perfil estacional del mes."""
    perfil = perfil or [1.0] * 12
    y, m = map(int, desde.split("-"))
    y_fin, m_fin = map(int, hasta.split("-"))
    rows = []
    while (y, m) <= (y_fin, m_fin):
        rev = nivel_por_anio[y] * perfil[m - 1]
        rows.append({"date": f"{y}-{m:02d}-01", "revenue": rev, "units": rev / 50,
                     "sessions": rev / 5, "cvr": 10, "buyBox": 95, "pageViews": 0,
                     "revenueB2B": 0, "spend": None, "ventasPPC": None})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# A. Invariantes sintéticos — definen qué tiene que cumplir el fix de fondo
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=True, reason=_BUG)
def test_negocio_plano_que_crece_tiene_indices_neutros():
    # Sin estacionalidad real: el crecimiento NO puede convertirse en estacionalidad.
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0})
    indices = rf.auto_detect_seasonality(hist)["indices"]
    assert indices == pytest.approx([1.0] * 12, abs=0.05)


@pytest.mark.xfail(strict=True, reason=_BUG)
def test_la_estacionalidad_real_se_conserva_aunque_la_cuenta_crezca():
    # Diciembre vale el doble que el resto. El fix tiene que conservar ESA señal: un
    # "fix" que aplane todo a 1.00 pasaría el test de arriba pero no este.
    perfil = [1.0] * 11 + [2.0]
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0}, perfil)
    indices = rf.auto_detect_seasonality(hist)["indices"]
    esperado = [p / (sum(perfil) / 12) for p in perfil]   # 0.923 x11, 1.846 dic
    assert indices == pytest.approx(esperado, rel=0.10)


@pytest.mark.xfail(strict=True, reason=_BUG)
def test_forecast_de_negocio_plano_no_cambia_al_aplicar_estacionalidad():
    # Consecuencia de la primera: si los índices salen neutros, tildar estacionalidad
    # no mueve la proyección de un negocio sin estacionalidad real.
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0})
    seasonality = rf.auto_detect_seasonality(hist)
    opts = {"horizon": 3, "momWindow": 3, "blend": 50}
    con = rf.generate_forecast({**opts, "useSeasonality": True}, hist, seasonality, "auto")
    sin = rf.generate_forecast({**opts, "useSeasonality": False}, hist, seasonality, "auto")
    assert [f["revenue"] for f in con] == pytest.approx([f["revenue"] for f in sin], rel=0.05)


# ═══════════════════════════════════════════════════════════════════════════
# B. Histórico real — formato y patrón del bug
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuenta", sorted(CUENTAS))
def test_fixture_real_tiene_el_formato_esperado(cuenta):
    rows = _historico_o_skip(cuenta)

    assert len(rows) >= _MIN_MESES, f"{cuenta}: {len(rows)} meses, mínimo {_MIN_MESES}"
    meses = [r["date"][:7] for r in rows]
    for anterior, actual in zip(meses, meses[1:]):
        assert rf._get_next_month_iso(f"{anterior}-01")[:7] == actual, \
            f"{cuenta}: hueco o desorden entre {anterior} y {actual}"
    assert all(r["revenue"] >= 0 for r in rows)


@pytest.mark.parametrize("cuenta", sorted(CUENTAS))
def test_cuenta_real_presenta_el_patron_del_bug(cuenta):
    # Con el cálculo de HOY: si el aviso de la Opción 3 se dispara, la cuenta tiene el
    # mecanismo (crecimiento fuerte + meses del forecast sin dato del año). Para
    # Trafilea este test ES la confirmación pendiente.
    rows = _historico_o_skip(cuenta)
    cfg = CUENTAS[cuenta]
    seasonality = rf.auto_detect_seasonality(rows)
    forecast = rf.generate_forecast(cfg["opts"], rows, seasonality, cfg["yoy_mode"])

    riesgo = rf._detectar_riesgo_estacionalidad(rows, forecast)

    if cfg["mismo_bug"] is None:
        pytest.skip(f"TODO({cuenta}): confirmar mecanismo. Resultado del detector: {riesgo}")
    assert (riesgo is not None) is cfg["mismo_bug"], f"{cuenta}: detector -> {riesgo}"


# ═══════════════════════════════════════════════════════════════════════════
# C. Números esperados por cuenta — el "número que cierra" según el AM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuenta", sorted(CUENTAS))
def test_forecast_real_cierra_con_lo_esperado(cuenta):
    # TODO(fix 1+4): con `esperado` completo este test falla con el cálculo actual.
    # Hasta que entre el fix, marcarlo xfail(strict=True, reason=_BUG) en la cuenta.
    cfg = CUENTAS[cuenta]
    if cfg["esperado"] is None:
        pytest.skip(f"TODO({cuenta}): completar CUENTAS['{cuenta}']['esperado']")
    rows = _historico_o_skip(cuenta)
    seasonality = rf.auto_detect_seasonality(rows)
    forecast = rf.generate_forecast(cfg["opts"], rows, seasonality, cfg["yoy_mode"])

    obtenido = {f["date"][:7]: f["revenue"] for f in forecast}
    for mes, valor in cfg["esperado"].items():
        assert obtenido.get(mes) == pytest.approx(valor, rel=cfg["tolerancia"]), \
            f"{cuenta} {mes}: forecast {obtenido.get(mes)} vs esperado {valor}"

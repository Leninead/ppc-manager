"""M31 — Tests de regresión del fix de fondo de estacionalidad.

Fix: Opción 1+4. `auto_detect_seasonality` compara cada mes con el nivel de su año
(efectos año + mes) y `generate_forecast` ya no aplica la estacionalidad dos veces.

  A. Invariantes SINTÉTICOS — qué tiene que cumplir el cálculo. No hace falta ningún
     dato real.

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

Cuentas (opts = los de producción, reproducidos con el motor anterior al fix):
  · tucann          — la cuenta de Goyo, reportada por Gregorio Martino. Bug confirmado.
  · the_sunny_zebra — control con estacionalidad real (pico jun/jul, piso dic).
  · dermaglos       — control plano, con la estacionalidad apagada.
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



# ═══════════════════════════════════════════════════════════════════════════
# Configuración por cuenta — COMPLETAR cuando llegue el histórico real
# ═══════════════════════════════════════════════════════════════════════════

CUENTAS: dict[str, dict] = {
    "tucann": {
        "archivo": "tucann_historico.csv",
        # True = bug confirmado; None = a confirmar con el histórico.
        "mismo_bug": True,
        "opts": {"horizon": 4, "momWindow": 12, "blend": 60, "useSeasonality": True},
        "yoy_mode": "auto",
        # TODO(tucann): proyección que "cierra" según el AM, por mes: {"2026-10": 123456.0}.
        "esperado": None,
        # Tolerancia relativa contra `esperado` (0.15 = ±15%).
        "tolerancia": 0.15,
    },
    "the_sunny_zebra": {
        "archivo": "the_sunny_zebra_historico.csv",
        "mismo_bug": False,
        "opts": {"horizon": 2, "momWindow": 5, "blend": 68, "useSeasonality": True},
        "yoy_mode": "auto",
        "esperado": None,
        "tolerancia": 0.15,
    },
    "dermaglos": {
        "archivo": "dermaglos_historico.csv",
        "mismo_bug": False,
        "opts": {"horizon": 3, "momWindow": 8, "blend": 63, "useSeasonality": False},
        "yoy_mode": "auto",
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

def test_negocio_plano_que_crece_tiene_indices_neutros():
    # Sin estacionalidad real: el crecimiento NO puede convertirse en estacionalidad.
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0})
    indices = rf.auto_detect_seasonality(hist)["indices"]
    assert indices == pytest.approx([1.0] * 12, abs=0.05)


def test_la_estacionalidad_real_se_conserva_aunque_la_cuenta_crezca():
    # Diciembre vale el doble que el resto. El fix tiene que conservar ESA señal: un
    # "fix" que aplane todo a 1.00 pasaría el test de arriba pero no este.
    perfil = [1.0] * 11 + [2.0]
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0}, perfil)
    indices = rf.auto_detect_seasonality(hist)["indices"]
    esperado = [p / (sum(perfil) / 12) for p in perfil]   # 0.923 x11, 1.846 dic
    assert indices == pytest.approx(esperado, rel=0.10)


def test_forecast_de_negocio_plano_no_cambia_al_aplicar_estacionalidad():
    # Consecuencia de la primera: si los índices salen neutros, tildar estacionalidad
    # no mueve la proyección de un negocio sin estacionalidad real.
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 22_000.0})
    seasonality = rf.auto_detect_seasonality(hist)
    opts = {"horizon": 3, "momWindow": 3, "blend": 50}
    con = rf.generate_forecast({**opts, "useSeasonality": True}, hist, seasonality, "auto")
    sin = rf.generate_forecast({**opts, "useSeasonality": False}, hist, seasonality, "auto")
    assert [f["revenue"] for f in con] == pytest.approx([f["revenue"] for f in sin], rel=0.05)


def test_la_proyeccion_mom_solo_se_mueve_de_la_estacion_del_mes_anterior():
    # Abril vende el doble que el resto y el último dato es abril (20.000). Sin la
    # temporada el negocio es plano, así que mayo vuelve a 10.000: ni arrastra el pico de
    # abril ni lee el salto mar→abr como crecimiento.
    perfil = [1.0] * 12
    perfil[3] = 2.0
    hist = _hist_sintetico("2025-01", "2026-04", {2025: 10_000.0, 2026: 10_000.0}, perfil)
    indices = [1.0] * 12
    indices[3] = 2.0
    opts = {"horizon": 1, "momWindow": 3, "blend": 50, "useSeasonality": True}
    forecast = rf.generate_forecast(opts, hist, {"enabled": True, "indices": indices}, "off")
    assert forecast[0]["date"].startswith("2026-05")
    assert forecast[0]["revenue"] == pytest.approx(10_000.0, rel=1e-9)
    assert forecast[0]["seasonality"] == 1.0


def test_un_mes_extremo_queda_acotado_por_el_clamp():
    perfil = [1.0] * 11 + [30.0]
    hist = _hist_sintetico("2025-01", "2026-08", {2025: 10_000.0, 2026: 10_000.0}, perfil)
    indices = rf.auto_detect_seasonality(hist)["indices"]
    assert indices[11] == rf._SEASON_INDEX_MAX
    assert min(indices) >= rf._SEASON_INDEX_MIN


def test_con_menos_de_13_meses_se_mantiene_el_calculo_anterior():
    hist = _hist_sintetico("2025-01", "2025-12", {2025: 10_000.0}, [1.0] * 11 + [2.0])
    assert rf.auto_detect_seasonality(hist)["indices"] == [0.923] * 11 + [1.846]


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


def test_tucann_la_estacionalidad_ya_no_aplasta_el_forecast():
    # Antes del fix el índice de septiembre era 0.106. El valle de sep-dic es real en los
    # datos de Tucann (oct-dic 2025 ≈ 8% de jun 2025), así que no sube a 1: sube a ~0.32.
    rows = _historico_o_skip("tucann")
    seasonality = rf.auto_detect_seasonality(rows)
    assert seasonality["indices"][8] > 0.30

    # Referencia: el mismo mes del año anterior crecido al YoY de la cuenta. Antes del fix,
    # con las opciones por default de la UI, sep/oct/nov quedaban en 17% / 5% / 5% de ella.
    opts = {"horizon": 3, "momWindow": 3, "blend": 50, "useSeasonality": True}
    forecast = rf.generate_forecast(opts, rows, seasonality, "auto")
    revenue_por_mes = {r["date"][:7]: r["revenue"] for r in rows}
    yoy = rf._yoy_growth("revenue", rows)
    for f in forecast:
        anio, mes = f["date"][:4], f["date"][5:7]
        referencia = revenue_por_mes[f"{int(anio) - 1}-{mes}"] * (1 + yoy)
        assert f["revenue"] >= referencia * 0.5, \
            f"{f['date'][:7]}: {f['revenue']:.0f} vs referencia del año anterior {referencia:.0f}"


def test_sunny_zebra_backtest_de_la_caida_de_otonio():
    # Con data hasta ago-2025, proyectar sep-dic 2025 con los settings de producción.
    # El motor anterior al fix erraba -21% / -57% / -78% / -82%.
    rows = [r for r in _historico_o_skip("the_sunny_zebra") if r["date"][:7] <= "2025-08"]
    real = {r["date"][:7]: r["revenue"] for r in _historico_o_skip("the_sunny_zebra")}
    cfg = CUENTAS["the_sunny_zebra"]
    forecast = rf.generate_forecast({**cfg["opts"], "horizon": 4}, rows,
                                    rf.auto_detect_seasonality(rows), cfg["yoy_mode"])

    assert [f["date"][:7] for f in forecast] == ["2025-09", "2025-10", "2025-11", "2025-12"]
    for f in forecast[:3]:
        mes = f["date"][:7]
        assert f["revenue"] == pytest.approx(real[mes], rel=0.30), \
            f"{mes}: forecast {f['revenue']:.0f} vs real {real[mes]:.0f}"
    # Diciembre sale +124%: con esta historia su índice sale de un solo dato (dic-2024).
    # La cota fija lo de hoy para que no empeore.
    assert forecast[3]["revenue"] <= real["2025-12"] * 2.5


def test_tucann_con_los_settings_de_produccion_no_queda_debajo_de_su_anio_anterior():
    # Producción mostraba sep-2026 en 11.640: 30% de sep-2025 crecido al YoY de la cuenta.
    rows = _historico_o_skip("tucann")
    cfg = CUENTAS["tucann"]
    forecast = rf.generate_forecast(cfg["opts"], rows, rf.auto_detect_seasonality(rows),
                                    cfg["yoy_mode"])
    sep_2025 = next(r["revenue"] for r in rows if r["date"].startswith("2025-09"))
    referencia = sep_2025 * (1 + rf._yoy_growth("revenue", rows))
    assert forecast[0]["date"].startswith("2026-09")
    assert forecast[0]["revenue"] >= referencia * 0.5


# ═══════════════════════════════════════════════════════════════════════════
# C. Números esperados por cuenta — el "número que cierra" según el AM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuenta", sorted(CUENTAS))
def test_forecast_real_cierra_con_lo_esperado(cuenta):
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

"""M31 F6.2 + F6.3 — Tests del forecast por-ASIN + helpers de tabla/totales.

Cubre las funciones PURAS de F6.3 (`_period_to_date`, `_asin_history_to_engine_rows`,
`_forecast_single_asin`) y los helpers PUROS de F6.2 (`_build_asin_child_df`,
`_asin_account_totals`). NO tocan Streamlit — sólo lógica.

Los tests reales reusan los 3 fixtures Dermaglos may/jun/jul 2026 (gitignored,
mismo skip guard que test_forecast_asin_accumulate.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures reales (gitignored — skip si falta alguno)
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures" / "real"
_CSVS = {p: _FIXTURES / f"dermaglos_asin_bychild_{p}.csv"
         for p in ("2026-05", "2026-06", "2026-07")}

_skip_no_fixtures = pytest.mark.skipif(
    not all(f.exists() for f in _CSVS.values()),
    reason="fixtures reales multi-mes gitignored ausentes")


def _load_model():
    snaps = [rf._parse_asin_report(str(_CSVS[p]), p)
             for p in ("2026-05", "2026-06", "2026-07")]
    return rf._accumulate_asin_snapshots(snaps)


_HERO = "B0CYLMJJJC"


# ─────────────────────────────────────────────────────────────────────────────
# Puros (sin fixtures)
# ─────────────────────────────────────────────────────────────────────────────

def test_period_to_date():
    assert rf._period_to_date("2026-05") == "2026-05-01"


def test_history_to_engine_rows_shape():
    history = [
        {"period": "2026-06", "revenue": 200.0, "units": 20.0,
         "sessions": 100.0, "unit_session_pct": 20.0},
        {"period": "2026-05", "revenue": 100.0, "units": 10.0,
         "sessions": 50.0, "unit_session_pct": 20.0},
    ]
    rows = rf._asin_history_to_engine_rows(history)
    # Ordenado asc por date (mayo antes que junio pese al orden de entrada).
    assert [r["date"] for r in rows] == ["2026-05-01", "2026-06-01"]
    for src, r in zip(sorted(history, key=lambda h: h["period"]), rows):
        assert set(r.keys()) == {"date", "revenue", "units", "sessions", "cvr"}
        assert r["cvr"] == src["unit_session_pct"]   # cvr == unit_session_pct


def test_forecast_single_asin_insufficient():
    history = [{"period": "2026-07", "revenue": 100.0, "units": 10.0,
                "sessions": 50.0, "unit_session_pct": 20.0}]
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    assert rf._forecast_single_asin(history, opts) == []


# ─────────────────────────────────────────────────────────────────────────────
# Reales (@_skip_no_fixtures)
# ─────────────────────────────────────────────────────────────────────────────

@_skip_no_fixtures
def test_forecast_single_asin_hero_real():
    model = _load_model()
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc = rf._forecast_single_asin(model[_HERO]["history"], opts)
    assert len(fc) == opts["horizon"]
    for row in fc:
        assert "revenue" in row
        assert "date" in row


@_skip_no_fixtures
def test_build_asin_child_df_real():
    model = _load_model()
    df = rf._build_asin_child_df(model)
    assert len(df) == 9                       # 9 ASINs
    assert df.isna().sum().sum() == 0         # sin NaN tras relleno con ''


@_skip_no_fixtures
def test_asin_account_totals_real():
    model = _load_model()
    totals = rf._asin_account_totals(model)
    assert [t["period"] for t in totals] == ["2026-05", "2026-06", "2026-07"]
    # Revenue del período más reciente > 0.
    assert totals[-1]["revenue"] > 0
    # Los totales sumados coinciden con la suma manual del model.
    manual_rev_jul = sum(
        h["revenue"] for node in model.values() for h in node["history"]
        if h["period"] == "2026-07"
    )
    assert totals[-1]["revenue"] == pytest.approx(manual_rev_jul)


@_skip_no_fixtures
def test_forecast_single_asin_partial_july():
    snaps = [rf._parse_asin_report(str(_CSVS[p]), p)
             for p in ("2026-05", "2026-06", "2026-07")]
    model = rf._accumulate_asin_snapshots(
        snaps, partial_periods={"2026-07": {"days_covered": 10}})
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    # El flag partial/days_covered NO debe romper el mapeo a engine rows
    # (el motor sólo usa date/revenue/units/sessions/cvr).
    fc = rf._forecast_single_asin(model[_HERO]["history"], opts)
    assert len(fc) == opts["horizon"]


# ─────────────────────────────────────────────────────────────────────────────
# F6.3b — exclusión de meses parciales del motor
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_excludes_partial_month():
    """Un mes partial=True NO debe influir en los VALORES del forecast: [A,B] y
    [A,B,C-partial] con A,B idénticos producen la MISMA secuencia de revenue (el
    crecimiento se ancla a los completos). Post-F6.3c las FECHAS sí difieren: el
    parcial corre el cursor un mes (fc_abc arranca un mes después que fc_ab)."""
    A = {"period": "2026-05", "revenue": 1000.0, "units": 100.0,
         "sessions": 500.0, "unit_session_pct": 20.0}
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    C_partial = {"period": "2026-07", "revenue": 300.0, "units": 30.0,
                 "sessions": 150.0, "unit_session_pct": 20.0, "partial": True}
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc_ab = rf._forecast_single_asin([A, B], opts)
    fc_abc = rf._forecast_single_asin([A, B, C_partial], opts)
    assert fc_ab, "control [A,B] no debería estar vacío"
    # Valores idénticos: el parcial no altera el crecimiento MoM.
    assert [r["revenue"] for r in fc_abc] == [r["revenue"] for r in fc_ab]
    # F6.3c: el parcial corre el cursor → fc_ab arranca jul, fc_abc arranca ago.
    assert [r["date"] for r in fc_ab] == ["2026-07-01", "2026-08-01", "2026-09-01"]
    assert [r["date"] for r in fc_abc] == ["2026-08-01", "2026-09-01", "2026-10-01"]


def test_forecast_partial_leaves_under_two_complete():
    """[B completo, C partial=True] → solo 1 completo → devuelve []."""
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    C_partial = {"period": "2026-07", "revenue": 300.0, "units": 30.0,
                 "sessions": 150.0, "unit_session_pct": 20.0, "partial": True}
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    assert rf._forecast_single_asin([B, C_partial], opts) == []


# ─────────────────────────────────────────────────────────────────────────────
# F6.3c — arranque en el mes siguiente al último CARGADO (incluye parcial)
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_starts_after_last_loaded_including_partial():
    """F6.3c: con un mes parcial al final, el forecast arranca en el mes SIGUIENTE
    al parcial (no re-proyecta el parcial ni el último completo)."""
    A = {"period": "2026-05", "revenue": 1000.0, "units": 100.0,
         "sessions": 500.0, "unit_session_pct": 20.0}
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    C_partial = {"period": "2026-07", "revenue": 300.0, "units": 30.0,
                 "sessions": 150.0, "unit_session_pct": 20.0, "partial": True}
    opts = {"horizon": 3, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc = rf._forecast_single_asin([A, B, C_partial], opts)
    assert fc, "debería proyectar con may+jun completos"
    assert fc[0]["date"] == "2026-08-01"   # mes sig al último cargado (jul parcial)
    assert [f["date"] for f in fc] == ["2026-08-01", "2026-09-01", "2026-10-01"]


def test_forecast_no_partial_starts_after_last_complete():
    """F6.3c no-op: sin meses parciales, el forecast arranca en el mes siguiente
    al último completo (idéntico al comportamiento pre-F6.3c)."""
    A = {"period": "2026-05", "revenue": 1000.0, "units": 100.0,
         "sessions": 500.0, "unit_session_pct": 20.0}
    B = {"period": "2026-06", "revenue": 1100.0, "units": 110.0,
         "sessions": 550.0, "unit_session_pct": 20.0}
    opts = {"horizon": 2, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc = rf._forecast_single_asin([A, B], opts)
    assert fc[0]["date"] == "2026-07-01"   # sin parcial → mes sig a junio
    assert [f["date"] for f in fc] == ["2026-07-01", "2026-08-01"]


def test_generate_forecast_start_from_none_is_noop():
    """El MVP global NO pasa start_from → el motor arranca en el mes siguiente a
    rows[-1] como siempre. Blindaje anti-regresión del path MVP."""
    rows = [
        {"date": "2026-05-01", "revenue": 1000.0, "units": 100.0, "sessions": 500.0, "cvr": 20.0},
        {"date": "2026-06-01", "revenue": 1100.0, "units": 110.0, "sessions": 550.0, "cvr": 20.0},
    ]
    seas = {"enabled": False, "indices": [1.0] * 12}
    opts = {"horizon": 2, "momWindow": 2, "blend": 50, "useSeasonality": False}
    fc_default = rf.generate_forecast(opts, rows, seas, "auto")
    fc_explicit_none = rf.generate_forecast(opts, rows, seas, "auto", start_from=None)
    assert fc_default[0]["date"] == "2026-07-01"
    assert [f["date"] for f in fc_default] == [f["date"] for f in fc_explicit_none]
    assert [f["revenue"] for f in fc_default] == [f["revenue"] for f in fc_explicit_none]


@_skip_no_fixtures
def test_forecast_hero_real_stable_not_crashing():
    """F6.3c: con julio marcado partial, el crecimiento MoM se ancla a may+jun
    completos (1818→1897, +~4%), pero el forecast ARRANCA en el mes siguiente al
    último CARGADO (julio parcial) → 2026-08, NO en julio (que las tablas ya
    muestran como real parcial). Revenue del primer mes sigue >1500 (~2066), no el
    ~287 desplomado que producía el parcial pre-F6.3b."""
    snaps = [rf._parse_asin_report(str(_CSVS[p]), p)
             for p in ("2026-05", "2026-06", "2026-07")]
    model = rf._accumulate_asin_snapshots(
        snaps, partial_periods={"2026-07": {"days_covered": 10}})
    fc = rf._forecast_single_asin(
        model[_HERO]["history"],
        {"horizon": 3, "momWindow": 2, "blend": 50})
    assert fc, "el hero debería proyectar con may+jun completos"
    assert fc[0]["date"] == "2026-08-01"   # F6.3c: mes sig al último CARGADO (jul parcial) → agosto
    assert fc[0]["revenue"] > 1500         # crecimiento sigue anclado a may+jun; solo se corre el cursor

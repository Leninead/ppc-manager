"""M31 F6.1b — Tests de la capa de acumulación multi-mes por-ASIN.

Cubre `_drop_parent_rollup` (descarta filas de rollup padre parent==child cuando
ese parent tiene otros children en el mismo snapshot) y `_accumulate_asin_snapshots`
(outer-join por child_asin de N snapshots → modelo con historial mensual ordenado).

Dos bloques:
  - REALES (@_skip_no_fixtures): valores CLAVADOS derivados de los 3 CSV reales
    Dermaglos may/jun/jul 2026 (gitignored). Skip si falta alguno.
  - SINTÉTICOS (dicts inline, NO gitignored): DEBEN pasar siempre — no dependen
    de fixtures, ejercen la lógica pura con casos mínimos y controlados.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures reales multi-mes (gitignored — skip si falta alguno)
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures" / "real"
_CSVS = {p: _FIXTURES / f"dermaglos_asin_bychild_{p}.csv"
         for p in ("2026-05", "2026-06", "2026-07")}

_skip_no_fixtures = pytest.mark.skipif(
    not all(f.exists() for f in _CSVS.values()),
    reason="fixtures reales multi-mes gitignored ausentes")


def _load_snapshots():
    return [rf._parse_asin_report(str(_CSVS[p]), p)
            for p in ("2026-05", "2026-06", "2026-07")]


_UNION = {"B0CY2XC91Z", "B0CYK4G2Y8", "B0CYKDSDJX", "B0CYL1RLNQ", "B0CYLDSQ5L",
          "B0CYLM4L23", "B0CYLMJJJC", "B0F4KXZVNM", "B0F548KTXD"}
_STANDALONE = {"B0CY2XC91Z", "B0CYK4G2Y8", "B0CYKDSDJX", "B0CYL1RLNQ", "B0CYLDSQ5L"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests reales (@_skip_no_fixtures)
# ─────────────────────────────────────────────────────────────────────────────

@_skip_no_fixtures
def test_drop_rollup_each_month_leaves_9_childs():
    for snap in _load_snapshots():
        assert len(rf._drop_parent_rollup(snap)) == 9


@_skip_no_fixtures
def test_rollup_parents_discarded():
    snaps = _load_snapshots()
    childs = {p: {r["child_asin"] for r in rf._drop_parent_rollup(snap)}
              for p, snap in zip(("2026-05", "2026-06", "2026-07"), snaps)}
    # B0FG84HMRN es rollup padre en mayo y junio → ausente como child tras drop.
    assert "B0FG84HMRN" not in childs["2026-05"]
    assert "B0FG84HMRN" not in childs["2026-06"]
    # B0FDX9XR56 es rollup padre en julio → ausente como child tras drop.
    assert "B0FDX9XR56" not in childs["2026-07"]


@_skip_no_fixtures
def test_standalone_preserved():
    for snap in _load_snapshots():
        childs = {r["child_asin"] for r in rf._drop_parent_rollup(snap)}
        assert _STANDALONE.issubset(childs)


@_skip_no_fixtures
def test_accumulate_union_is_9():
    model = rf._accumulate_asin_snapshots(_load_snapshots())
    assert len(model) == 9
    assert set(model) == _UNION


@_skip_no_fixtures
def test_hero_history_3_months_clavado():
    model = rf._accumulate_asin_snapshots(_load_snapshots())
    h = model["B0CYLMJJJC"]["history"]
    assert [x["period"] for x in h] == ["2026-05", "2026-06", "2026-07"]
    m05, m06, m07 = h
    assert m05["sessions"] == 1512
    assert m05["units"] == 183
    assert m05["revenue"] == pytest.approx(1818.18)
    assert m06["sessions"] == 1176
    assert m06["units"] == 205
    assert m06["revenue"] == pytest.approx(1897.45)
    assert m07["sessions"] == 243
    assert m07["units"] == 45
    assert m07["revenue"] == pytest.approx(449.55)


@_skip_no_fixtures
def test_history_sorted_ascending():
    model = rf._accumulate_asin_snapshots(_load_snapshots())
    for node in model.values():
        periods = [x["period"] for x in node["history"]]
        assert periods == sorted(periods)


@_skip_no_fixtures
def test_partial_flag_stamped_on_july():
    model = rf._accumulate_asin_snapshots(
        _load_snapshots(), partial_periods={"2026-07": {"days_covered": 10}})
    hist = {x["period"]: x for x in model["B0CYLMJJJC"]["history"]}
    assert hist["2026-07"]["partial"] is True
    assert hist["2026-07"]["days_covered"] == 10
    # may/jun NO deben llevar el flag partial.
    assert hist["2026-05"].get("partial") is not True
    assert hist["2026-06"].get("partial") is not True


# ─────────────────────────────────────────────────────────────────────────────
# Tests sintéticos (dicts inline, NO gitignored — DEBEN pasar siempre)
# ─────────────────────────────────────────────────────────────────────────────

def _row(parent, child, period, title="t", **metrics):
    base = {"parent_asin": parent, "child_asin": child, "title": title,
            "period": period, "sessions": 0.0, "page_views": 0.0,
            "buy_box_pct": 0.0, "units": 0.0, "unit_session_pct": 0.0,
            "revenue": 0.0}
    base.update(metrics)
    return base


def test_drop_rollup_synthetic():
    # P1 con dos children C1,C2 + su fila rollup P1/P1 + standalone S1/S1.
    snap = [
        _row("P1", "C1", "2026-01"),
        _row("P1", "C2", "2026-01"),
        _row("P1", "P1", "2026-01"),   # rollup → fuera (P1 tiene otros children)
        _row("S1", "S1", "2026-01"),   # standalone → dentro (único de S1)
    ]
    kept = {r["child_asin"] for r in rf._drop_parent_rollup(snap)}
    assert kept == {"C1", "C2", "S1"}


def test_accumulate_outer_join_asin_missing_one_month():
    # mes1 tiene {A,B}, mes2 tiene {A,C} (parent != child → nunca son rollup).
    mes1 = [_row("PA", "A", "2026-01"), _row("PB", "B", "2026-01")]
    mes2 = [_row("PA", "A", "2026-02"), _row("PC", "C", "2026-02")]
    model = rf._accumulate_asin_snapshots([mes1, mes2])
    assert len(model["A"]["history"]) == 2
    assert len(model["B"]["history"]) == 1
    assert len(model["C"]["history"]) == 1
    assert [x["period"] for x in model["B"]["history"]] == ["2026-01"]
    assert [x["period"] for x in model["C"]["history"]] == ["2026-02"]


def test_accumulate_parent_title_from_latest():
    mes1 = [_row("PA", "A", "2026-01", title="viejo")]
    mes2 = [_row("PA", "A", "2026-02", title="nuevo")]
    model = rf._accumulate_asin_snapshots([mes1, mes2])
    assert model["A"]["title"] == "nuevo"


def test_partial_absent_when_not_passed():
    mes1 = [_row("PA", "A", "2026-01")]
    mes2 = [_row("PA", "A", "2026-02")]
    model = rf._accumulate_asin_snapshots([mes1, mes2])
    for node in model.values():
        for entry in node["history"]:
            assert "partial" not in entry

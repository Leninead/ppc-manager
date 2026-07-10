"""M31 F6.1a — Tests del parser de UN snapshot por-ASIN.

Scope acotado: `_parse_asin_report` (lee un CSV "Detail Page Sales and Traffic
By Child Item" de un mes → lista de ASINs con métricas) + `_is_asin_report`
(detección de formato por presencia de "(Child) ASIN" en el header).

NADA de acumulación multi-mes, UI, forecast ni Keepa (eso es F6.1b+). El mes
al que corresponde el snapshot se pasa como PARÁMETRO `period` (el reporte NO
tiene columna Date), no se infiere.

Estrategia de tests (misma convención que test_revenue_forecast_parser.py):
    1. Detección (`_is_asin_report`): headers inline clavados (raw string y
       lista de columnas), True para el por-ASIN, False para el by-date del MVP.
    2. Fixture real (`tests/fixtures/real/dermaglos_asin_bychild_2026-07.csv`):
       gitignored (dato de cliente Dermaglos). `skipif(not exists)` para que
       la suite no rompa donde falte. Valores esperados DERIVADOS
       INDEPENDIENTEMENTE (pandas crudo) — NO usamos el output del parser bajo
       test como golden.
    3. Mini-CSV sintético inline (bytes, no gitignored): reproduce el formato
       real ($, comas, %, títulos con comas internas) sin depender del fixture.

NOTA sobre el conteo de filas: el fixture real tiene 10 filas de datos, no 9.
La fila #10 es el ASIN padre B0FDX9XR56 apareciendo como su propia fila child
(sessions=1, units=0, revenue=$0.00) — comportamiento normal de Amazon en el
export "By Child Item". El parser es un snapshot puro: NO filtra, devuelve
todas las filas tal cual. El rollup padre/hijo es F6.1b+.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from modules.pages import revenue_forecast as rf


# ─────────────────────────────────────────────────────────────────────────────
# Fixture path (gitignored — skip si no está)
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real"
_ASIN_FIXTURE = _FIXTURES_DIR / "dermaglos_asin_bychild_2026-07.csv"

_PERIOD = "2026-07"

# Shape interno esperado (10 claves snake_case).
_EXPECTED_KEYS = {
    "parent_asin",
    "child_asin",
    "title",
    "sessions",
    "page_views",
    "buy_box_pct",
    "units",
    "unit_session_pct",
    "revenue",
    "period",
}

# Header real del reporte por-ASIN (21 columnas, con BOM en la primera).
_ASIN_HEADER_RAW = (
    "﻿(Parent) ASIN,(Child) ASIN,Title,Sessions - Total,"
    "Sessions - Total - B2B,Session Percentage - Total,"
    "Session Percentage - Total - B2B,Page Views - Total,"
    "Page Views - Total - B2B,Page Views Percentage - Total,"
    "Page Views Percentage - Total - B2B,Featured Offer (Buy Box) Percentage,"
    "Featured Offer (Buy Box) Percentage - B2B,Units Ordered,"
    "Units Ordered - B2B,Unit Session Percentage,"
    "Unit Session Percentage - B2B,Ordered Product Sales,"
    "Ordered Product Sales - B2B,Total Order Items,Total Order Items - B2B"
)

# Header representativo del reporte by-date del MVP (tiene Date, NO tiene
# "(Child) ASIN").
_BYDATE_HEADER_RAW = (
    "Date,Ordered Product Sales,Units Ordered,Total Order Items,"
    "Sessions - Total,Page Views - Total,"
    "Featured Offer (Buy Box) Percentage,Unit Session Percentage"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper de derivación INDEPENDIENTE (no usa el parser bajo test).
# ─────────────────────────────────────────────────────────────────────────────

def _raw_expected() -> dict[str, dict]:
    """Lee el fixture con pandas crudo y deriva el shape esperado por child ASIN,
    limpiando la moneda/comas/% a mano (independiente de `_parse_num`)."""
    df = pd.read_csv(
        _ASIN_FIXTURE, dtype=str, encoding="utf-8-sig", keep_default_na=False
    )

    def _num(s: str) -> float:
        s = s.replace("$", "").replace("%", "").replace(",", "").strip()
        return float(s) if s not in ("", "-") else 0.0

    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        out[r["(Child) ASIN"]] = {
            "parent_asin": r["(Parent) ASIN"].strip(),
            "sessions": _num(r["Sessions - Total"]),
            "page_views": _num(r["Page Views - Total"]),
            "buy_box_pct": _num(r["Featured Offer (Buy Box) Percentage"]),
            "units": _num(r["Units Ordered"]),
            "unit_session_pct": _num(r["Unit Session Percentage"]),
            "revenue": _num(r["Ordered Product Sales"]),
            "title": r["Title"].strip(),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# _is_asin_report — detección de formato (sin routing)
# ─────────────────────────────────────────────────────────────────────────────

def test_is_asin_report_true_from_raw_header_string():
    assert rf._is_asin_report(_ASIN_HEADER_RAW) is True


def test_is_asin_report_true_from_column_list():
    cols = ["(Parent) ASIN", "(Child) ASIN", "Title", "Sessions - Total"]
    assert rf._is_asin_report(cols) is True


def test_is_asin_report_false_for_bydate_header():
    assert rf._is_asin_report(_BYDATE_HEADER_RAW) is False


def test_is_asin_report_false_for_none():
    assert rf._is_asin_report(None) is False


# ─────────────────────────────────────────────────────────────────────────────
# _parse_asin_report — fixture real (gitignored)
# ─────────────────────────────────────────────────────────────────────────────

_skip_no_fixture = pytest.mark.skipif(
    not _ASIN_FIXTURE.exists(), reason="fixture real gitignored ausente"
)


@_skip_no_fixture
def test_parse_returns_all_rows():
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    # 10 filas: 9 children + 1 fila del ASIN padre B0FDX9XR56 (sess 1, u 0).
    assert len(rows) == 10


@_skip_no_fixture
def test_parse_each_row_has_full_shape():
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    for row in rows:
        assert set(row.keys()) == _EXPECTED_KEYS


@_skip_no_fixture
def test_parse_period_stamped_on_every_row():
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    assert all(row["period"] == _PERIOD for row in rows)


@_skip_no_fixture
def test_parse_hero_asin_clavado_values():
    """B0CYLMJJJC (hero Dermaglos): valores específicos derivados del CSV real."""
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    hero = next(r for r in rows if r["child_asin"] == "B0CYLMJJJC")
    assert hero["parent_asin"] == "B0FDX9XR56"
    assert hero["sessions"] == 243           # "243"
    assert hero["page_views"] == 310         # "310"
    assert hero["buy_box_pct"] == pytest.approx(98.98)   # "98.98%"
    assert hero["units"] == 45
    assert hero["unit_session_pct"] == pytest.approx(18.52)  # CVR "18.52%"
    assert hero["revenue"] == pytest.approx(449.55)      # "$449.55"


@_skip_no_fixture
def test_parse_parent_self_zero_row():
    """La fila del padre B0FDX9XR56 (child==parent) con actividad casi nula."""
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    parent_row = next(r for r in rows if r["child_asin"] == "B0FDX9XR56")
    assert parent_row["parent_asin"] == "B0FDX9XR56"
    assert parent_row["sessions"] == 1
    assert parent_row["units"] == 0
    assert parent_row["revenue"] == 0.0      # "$0.00" → 0.0


@_skip_no_fixture
def test_parse_title_with_internal_commas_intact():
    """Los títulos largos con comas internas NO rompen el parseo (quoting)."""
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    hero = next(r for r in rows if r["child_asin"] == "B0CYLMJJJC")
    # El título real tiene comas internas ("Vitamin A (Retinoids), Vitamin E...").
    assert "Vitamin A" in hero["title"]
    assert "," in hero["title"]  # confirma que preservó comas internas


@_skip_no_fixture
def test_parse_matches_independent_derivation_all_rows():
    """Cada valor del parser coincide con la derivación pandas-cruda independiente."""
    rows = rf._parse_asin_report(str(_ASIN_FIXTURE), _PERIOD)
    expected = _raw_expected()
    assert len(rows) == len(expected)
    for row in rows:
        exp = expected[row["child_asin"]]
        assert row["parent_asin"] == exp["parent_asin"]
        assert row["sessions"] == pytest.approx(exp["sessions"])
        assert row["page_views"] == pytest.approx(exp["page_views"])
        assert row["buy_box_pct"] == pytest.approx(exp["buy_box_pct"])
        assert row["units"] == pytest.approx(exp["units"])
        assert row["unit_session_pct"] == pytest.approx(exp["unit_session_pct"])
        assert row["revenue"] == pytest.approx(exp["revenue"])
        assert row["title"] == exp["title"]


# ─────────────────────────────────────────────────────────────────────────────
# _parse_asin_report — mini-CSV sintético inline (bytes, no gitignored)
# ─────────────────────────────────────────────────────────────────────────────

# 2 filas. Reproduce: $ + coma de miles + comillas, %, título con comas internas,
# y una fila en cero ($0.00). Header con las columnas core + un par de B2B para
# verificar que NO se confunden con las Total.
_SYNTH_CSV = (
    "(Parent) ASIN,(Child) ASIN,Title,Sessions - Total,Sessions - Total - B2B,"
    "Page Views - Total,Featured Offer (Buy Box) Percentage,Units Ordered,"
    "Unit Session Percentage,Ordered Product Sales\n"
    'PARENT1,CHILD1,"Cream, Vitamin A & E, 1,76 oz","1,128",13,"1,492",'
    '99.34%,209,18.53%,"$1,937.41"\n'
    'PARENT2,CHILD2,"Simple Title",100,0,120,100.00%,0,0.00%,$0.00\n'
).encode("utf-8")


def test_parse_synthetic_money_and_thousands():
    rows = rf._parse_asin_report(_SYNTH_CSV, _PERIOD)
    assert len(rows) == 2
    c1 = next(r for r in rows if r["child_asin"] == "CHILD1")
    assert c1["revenue"] == pytest.approx(1937.41)   # "$1,937.41"
    assert c1["sessions"] == 1128                     # "1,128"
    assert c1["page_views"] == 1492                   # "1,492"
    assert c1["units"] == 209
    assert c1["unit_session_pct"] == pytest.approx(18.53)  # "18.53%"


def test_parse_synthetic_zero_revenue():
    rows = rf._parse_asin_report(_SYNTH_CSV, _PERIOD)
    c2 = next(r for r in rows if r["child_asin"] == "CHILD2")
    assert c2["revenue"] == 0.0    # "$0.00"
    assert c2["units"] == 0


def test_parse_synthetic_percentage():
    rows = rf._parse_asin_report(_SYNTH_CSV, _PERIOD)
    c1 = next(r for r in rows if r["child_asin"] == "CHILD1")
    assert c1["buy_box_pct"] == pytest.approx(99.34)   # "35.74%"-style parse


def test_parse_synthetic_title_commas_intact():
    rows = rf._parse_asin_report(_SYNTH_CSV, _PERIOD)
    c1 = next(r for r in rows if r["child_asin"] == "CHILD1")
    assert c1["title"] == "Cream, Vitamin A & E, 1,76 oz"


def test_parse_synthetic_period_stamped():
    rows = rf._parse_asin_report(_SYNTH_CSV, _PERIOD)
    assert all(r["period"] == _PERIOD for r in rows)


def test_parse_synthetic_b2b_not_confused_with_total():
    """Sessions - Total = 1128 debe ganar sobre Sessions - Total - B2B = 13."""
    rows = rf._parse_asin_report(_SYNTH_CSV, _PERIOD)
    c1 = next(r for r in rows if r["child_asin"] == "CHILD1")
    assert c1["sessions"] == 1128   # NO 13 (la B2B)

"""Tests de los parsers DataDive extraídos a modules/parsers/datadive.py.

E1: foco en el fix del bug NaN de parse_mkl (D4). El set completo de tests del
parser llega en E2.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from modules.parsers.datadive import parse_mkl, parse_competitors, parse_rank_radar

# Layout esperado por parse_mkl (read con header=None):
#   col0=index, col1=Search Term, col2=SV, col3=Relevance, col4=Sugg.Bid,
#   col5=Launch Score, col6+=rank por ASIN. La fila 0 contiene "Search Term"
#   (para detección de header) y el ASIN en col6 (para detección de competidor).
_MKL_HEADER = [None, "Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score", "B0TEST00001"]


def _mkl_bytes(data_rows: list[list]) -> bytes:
    """Construye bytes de un .xlsx MKL sintético con el layout que espera parse_mkl."""
    df = pd.DataFrame([_MKL_HEADER] + data_rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


def test_parse_mkl_handles_nan_sv_without_crash():
    """Una fila con SV vacío (NaN) no debe crashear y SV debe coercionarse a 0.

    Bug original: `pd.to_numeric(...) or 0` devuelve NaN (NaN es truthy), y luego
    `int(NaN)` lanza ValueError.
    """
    data = _mkl_bytes([
        [1, "yoga mat", 1000, 5.5, 1.20, 8.0, 3],
        [2, "foam roller", None, 4.0, 0.90, 6.0, None],  # SV vacío → NaN
    ])
    df, _asins = parse_mkl(data, "synthetic.xlsx")
    assert len(df) == 2
    foam = df[df["Search Term"] == "foam roller"].iloc[0]
    assert foam["SV"] == 0


def test_parse_mkl_coerces_nan_relevance_and_launch_to_zero():
    """Relevance / Launch Score NaN deben quedar en 0, no NaN."""
    data = _mkl_bytes([
        [1, "kw a", 500, None, 1.0, None, 5],  # Relevance + Launch NaN
    ])
    df, _asins = parse_mkl(data, "synthetic.xlsx")
    row = df.iloc[0]
    assert row["Relevance"] == 0
    assert row["Launch Score"] == 0


# ── Builders adicionales (E2) ────────────────────────────────────────────────

def _sheet_bytes(rows: list[list]) -> bytes:
    """Construye bytes de un .xlsx con las filas dadas tal cual (header=None)."""
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


# ── parse_mkl — set completo (E2) ────────────────────────────────────────────

def test_parse_mkl_extracts_keywords_with_asin_ranks():
    header = [None, "Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score",
              "B0AAA00001", "B0BBB00002", "B0CCC00003"]
    rows = [
        header,
        [1, "yoga mat", 1000, 5.5, 1.20, 8.0, 3, 12, None],
        [2, "foam roller", 500, 4.0, 0.90, 6.0, None, 7, 40],
    ]
    df, asins = parse_mkl(_sheet_bytes(rows), "mkl.xlsx")
    assert asins == ["B0AAA00001", "B0BBB00002", "B0CCC00003"]
    for a in asins:
        assert a in df.columns
    yoga = df[df["Search Term"] == "yoga mat"].iloc[0]
    assert yoga["B0AAA00001"] == 3
    # OJO: el parser guarda None, pero pandas upcastea la columna mixta int/None
    # a float64 → el faltante queda como NaN, no None. El mapper (E3) debe usar
    # pd.isna(), no `is None`, para detectar ranks faltantes.
    assert pd.isna(yoga["B0CCC00003"])


def test_parse_mkl_detects_asin_in_header_row_or_below():
    # El ASIN puede estar en cualquiera de las 3 primeras filas de su columna.
    rows = [
        [None, "Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score", "B0AAA00001", None, None],
        [None, None, None, None, None, None, None, "B0BBB00002", None],
        [None, None, None, None, None, None, None, None, "B0CCC00003"],
        [1, "kw uno", 100, 2.0, 0.5, 5.0, 1, 2, 3],
    ]
    df, asins = parse_mkl(_sheet_bytes(rows), "mkl.xlsx")
    assert set(asins) == {"B0AAA00001", "B0BBB00002", "B0CCC00003"}
    assert df.shape[0] == 1  # solo "kw uno" es fila de datos válida


def test_parse_mkl_skips_empty_search_term_rows():
    header = [None, "Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score", "B0AAA00001"]
    rows = [
        header,
        [1, "valid one", 100, 2.0, 0.5, 5.0, 1],
        [2, "", 100, 2.0, 0.5, 5.0, 1],      # term vacío
        [3, "nan", 100, 2.0, 0.5, 5.0, 1],   # "nan" literal
        [4, None, 100, 2.0, 0.5, 5.0, 1],    # None
        [5, "valid two", 200, 3.0, 0.6, 6.0, 2],
    ]
    df, _ = parse_mkl(_sheet_bytes(rows), "mkl.xlsx")
    assert df.shape[0] == 2
    assert set(df["Search Term"]) == {"valid one", "valid two"}


def test_parse_mkl_handles_no_asin_columns():
    header = [None, "Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score"]
    rows = [
        header,
        [1, "kw uno", 100, 2.0, 0.5, 5.0],
        [2, "kw dos", 200, 3.0, 0.6, 6.0],
    ]
    df, asins = parse_mkl(_sheet_bytes(rows), "mkl.xlsx")
    assert asins == []
    assert df.shape[0] == 2
    for col in ["Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score"]:
        assert col in df.columns


def test_parse_mkl_coerces_sv_with_commas():
    header = [None, "Search Term", "SV", "Relevance", "Sugg. Bid", "Launch Score", "B0AAA00001"]
    rows = [header, [1, "big kw", "12,450", 5.0, 1.0, 7.0, 2]]
    df, _ = parse_mkl(_sheet_bytes(rows), "mkl.xlsx")
    assert df.iloc[0]["SV"] == 12450


def test_parse_mkl_garbage_input_raises():
    # El plan lo nombró "returns_empty", pero el comportamiento real de
    # pd.read_excel sobre bytes no-xlsx es LANZAR. Caracterizamos el raise
    # (no se modifica el parser en E2 — sería un cambio de comportamiento).
    with pytest.raises(Exception):
        parse_mkl(b"not an xlsx", "garbage.bin")


# ── parse_mkl — 2026-08 layout ("Type" column plus renamed headers) ──────────

_MKL_HEADER_2026 = [None, "Search Terms", "Type", "SV", "Relev.",
                    "Sugg. bid & range", "Launch Score", "B0AAA00001", "B0BBB00002"]


def test_parse_mkl_maps_columns_by_header_name_new_layout():
    """The fresh export inserted "Type" and shifted the whole layout: mapping by
    header name must still pull the right columns."""
    rows = [
        _MKL_HEADER_2026,
        [None, "hair serum", None, 119293, 0.888889, "$0.06 | $0.04 - $0.08", 403, 1, None],
        [None, "hair syrum", None, 250, 1, "$0.01 | $0.00 - $0.01", 1, 1, 5],
    ]
    df, asins = parse_mkl(_sheet_bytes(rows), "niche-XXX-keywords.xlsx")
    assert asins == ["B0AAA00001", "B0BBB00002"]
    serum = df[df["Search Term"] == "hair serum"].iloc[0]
    assert serum["SV"] == 119293
    assert serum["Sugg. Bid"] == pytest.approx(0.06)
    assert serum["Launch Score"] == 403
    assert serum["B0AAA00001"] == 1
    assert pd.isna(serum["B0BBB00002"])


def test_parse_mkl_rescales_fraction_relevance_to_ui_scale():
    """Fractional 0-1 relevancy (the new format) is rescaled to the UI's 0-10."""
    rows = [
        _MKL_HEADER_2026,
        [None, "kw uno", None, 500, 0.444444, "$0.50 | $0.40 - $0.60", 3, 1, None],
        [None, "kw dos", None, 300, 1.0, "$0.30 | $0.20 - $0.40", 2, None, 4],
    ]
    df, _ = parse_mkl(_sheet_bytes(rows), "niche-XXX-keywords.xlsx")
    uno = df[df["Search Term"] == "kw uno"].iloc[0]
    dos = df[df["Search Term"] == "kw dos"].iloc[0]
    assert uno["Relevance"] == pytest.approx(4.44, abs=0.001)
    assert dos["Relevance"] == pytest.approx(10.0)


def test_parse_mkl_legacy_scale_relevance_not_rescaled():
    """Any value above 1 means the file is already 0-10, so leave it alone."""
    data = _mkl_bytes([
        [1, "kw a", 500, 5.5, 1.0, 7.0, 3],
        [2, "kw b", 300, 0.5, 0.8, 6.0, 1],
    ])
    df, _ = parse_mkl(data, "legacy.xlsx")
    assert df[df["Search Term"] == "kw a"].iloc[0]["Relevance"] == 5.5
    assert df[df["Search Term"] == "kw b"].iloc[0]["Relevance"] == 0.5


# ── parse_competitors (E2) ───────────────────────────────────────────────────

def test_parse_competitors_extracts_median_and_asin_rows():
    rows = [
        ["Metric", "Median", "", "", "", "Comp 1", "Comp 2"],
        ["ASIN", "", "", "", "", "B0AAA00001", "B0BBB00002"],
        ["Price", "20.00", "", "", "", "19.99", "21.00"],
        ["Rating", "4.5", "", "", "", "4.4", "4.6"],
    ]
    df, median_data = parse_competitors(_sheet_bytes(rows), "comp.xlsx")
    assert not df.empty
    assert df.shape[0] == 2
    assert set(df["ASIN"]) == {"B0AAA00001", "B0BBB00002"}
    assert "Price" in median_data


# ── parse_rank_radar (E2) ─────────────────────────────────────────────────────

def test_parse_rank_radar_extracts_date_columns():
    rows = [
        ["", "", "Organic", "Organic", "Organic"],
        ["Search Terms", "SV", "2025-01-01", "2025-02-01", "2025-03-01"],
        ["", "", 5, 6, 7],
        ["", "", "", "", ""],
        ["yoga mat", 1000, 3, 4, 5],
        ["foam roller", 500, 10, 9, 8],
    ]
    df, date_cols, _agg = parse_rank_radar(_sheet_bytes(rows), "rr.xlsx")
    assert date_cols == ["2025-01-01", "2025-02-01", "2025-03-01"]
    for d in date_cols:
        assert d in df.columns
    assert df.shape[0] == 2

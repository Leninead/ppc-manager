"""Tests de los parsers DataDive extraídos a modules/parsers/datadive.py.

E1: foco en el fix del bug NaN de parse_mkl (D4). El set completo de tests del
parser llega en E2.
"""
from __future__ import annotations

import io

import pandas as pd

from modules.parsers.datadive import parse_mkl

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

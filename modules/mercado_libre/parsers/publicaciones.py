"""Parser for the 'Modifica tus publicaciones' export (stock and status).

File structure: three sheets, the data lives in 'Publicaciones'. Row 0
carries the technical column names (ITEM_ID, STOCK_FLEX, STATUS) and rows 1
to 5 are Mercado Libre help text. Data starts at row 6.

We use the technical names, not the Spanish labels, because the first are
stable across exports while the second change with the account language.
"""
from __future__ import annotations

import pandas as pd

from .common import normalize_mla, normalize_text, to_decimal, to_int

_SHEET = "Publicaciones"
_TECHNICAL_ROW = 0
_FIRST_DATA_ROW = 6

_REQUIRED_COLUMNS = {"ITEM_ID", "STOCK_FLEX", "STATUS"}

# Tracking excludes listings that cannot sell.
_EXCLUDED_STATES = {"pausada", "inactiva", "finalizada", "cerrada", "bajo revision"}


class FormatError(Exception):
    """The file is not shaped like the expected listings export."""


def parse(file, exclude_inactive: bool = True) -> pd.DataFrame:
    try:
        raw = pd.read_excel(file, sheet_name=_SHEET, header=None)
    except ValueError as exc:
        raise FormatError(
            f"El archivo no tiene una hoja llamada '{_SHEET}'. Verificá que sea "
            "el export de 'Modifica tus publicaciones' sin modificar."
        ) from exc

    technical = [str(c).strip() for c in raw.iloc[_TECHNICAL_ROW].tolist()]
    missing = _REQUIRED_COLUMNS - set(technical)
    if missing:
        raise FormatError(
            "Al export le faltan columnas esperadas: " + ", ".join(sorted(missing))
        )

    df = raw.iloc[_FIRST_DATA_ROW:].copy()
    df.columns = technical

    cleaned = pd.DataFrame()
    cleaned["mla"] = df["ITEM_ID"].map(normalize_mla)
    cleaned["variacion"] = df.get("VARIATION_ID")
    cleaned["sku"] = df.get("SKU")
    cleaned["titulo"] = df.get("TITLE", pd.Series(dtype=object)).astype(str).str.strip()
    cleaned["stock"] = df["STOCK_FLEX"].map(to_int)
    cleaned["precio"] = df.get("PRICE", pd.Series(dtype=object)).map(to_decimal)
    cleaned["estado"] = df["STATUS"].map(normalize_text)

    cleaned = cleaned[cleaned["mla"].notna()].copy()
    cleaned["stock"] = cleaned["stock"].fillna(0)

    if exclude_inactive:
        cleaned = cleaned[~cleaned["estado"].isin(_EXCLUDED_STATES)].copy()

    # The export breaks stock out per variant; the rest of the module works
    # at listing level, so we sum the stock and keep the per-variant detail
    # on the side.
    aggregated = (
        cleaned.groupby("mla", as_index=False)
        .agg(
            titulo=("titulo", "first"),
            estado=("estado", "first"),
            stock=("stock", "sum"),
            precio=("precio", "median"),
            variantes=("mla", "size"),
        )
    )
    # The schema declares stock as float64 because the parser fills missing
    # STOCK_FLEX cells with zero. When the export happens to have no blanks
    # the sum stays int64 and _validate_against_schema refuses the snapshot
    # ("Tipo incorrecto en 'stock': esperado float64, recibido int64"). Cast
    # explicitly so the dtype is stable regardless of the export.
    aggregated["stock"] = aggregated["stock"].astype("float64")
    # Schema v2 introduced "origen" so a single Parquet can carry both
    # Excel-parsed and API-materialised rows. The parser is the Excel side.
    aggregated["origen"] = "excel"
    return aggregated

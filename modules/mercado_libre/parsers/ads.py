"""Parser for the Mercado Libre Product Ads report.

Structure: three sheets, the data lives in 'Reporte por Anuncios'. Row 0
holds a grouping title, column names sit in row 1 and carry newline-embedded
definitions per metric. Data starts at row 2, with the period dates repeated
on every row.

Ads without activity export '-' in the derived metrics (CPC, CTR, ACOS,
ROAS). We keep that dash as missing data instead of turning it into zero:
an ad with no impressions does not have a ROAS of 0, it has no ROAS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .common import normalize_mla, normalize_text, to_decimal, to_int

_SHEET = "Reporte por Anuncios"
_HEADER_ROW = 1

_MONTH_ABBR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_REQUIRED_COLUMNS = {"campana", "numero de publicacion", "impresiones", "clics"}


@dataclass
class AdsReport:
    datos: pd.DataFrame
    desde: date | None
    hasta: date | None


class FormatError(Exception):
    """The file is not shaped like the expected ads report."""


def _parse_date(value) -> date | None:
    """Parse the '09-jul-2026' format used by the ads report."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    text = normalize_text(value)
    match = re.match(r"(\d{1,2})-([a-z]{3})-(\d{4})", text)
    if not match:
        return None
    day, month, year = match.groups()
    month_num = _MONTH_ABBR.get(month)
    if month_num is None:
        return None
    return date(int(year), month_num, int(day))


def _shorten_header(name) -> str:
    """Clean up the header, which carries the metric definition in the cell.

    Newlines show up both separating the definition ('ACOS\n(Inversión /
    Ingresos)') and splitting the name itself ('Número de \npublicación'),
    so we drop everything inside parentheses instead of cutting on the
    newline.
    """
    text = str(name).replace("\n", " ")
    text = re.sub(r"\(.*?\)?$", "", text)
    return normalize_text(text)


def parse(file) -> AdsReport:
    try:
        raw = pd.read_excel(file, sheet_name=_SHEET, header=None)
    except ValueError as exc:
        raise FormatError(
            f"El archivo no tiene una hoja llamada '{_SHEET}'. Verificá que sea "
            "el reporte de publicidad sin modificar."
        ) from exc

    headers = [_shorten_header(c) for c in raw.iloc[_HEADER_ROW].tolist()]
    missing = _REQUIRED_COLUMNS - set(headers)
    if missing:
        raise FormatError(
            "Al reporte de ads le faltan columnas esperadas: "
            + ", ".join(sorted(missing))
        )

    df = raw.iloc[_HEADER_ROW + 1:].copy()
    df.columns = headers

    cleaned = pd.DataFrame()
    cleaned["desde"] = df["desde"].map(_parse_date)
    cleaned["hasta"] = df["hasta"].map(_parse_date)
    cleaned["campana"] = df["campana"].astype(str).str.strip()
    cleaned["anuncio"] = df.get("titulo de anuncio", pd.Series(dtype=object)).astype(str).str.strip()
    cleaned["mla"] = df["numero de publicacion"].map(normalize_mla)
    cleaned["estado"] = df.get("estado", pd.Series(dtype=object)).map(normalize_text)
    cleaned["impresiones"] = df["impresiones"].map(to_int).fillna(0).astype(int)
    cleaned["clics"] = df["clics"].map(to_int).fillna(0).astype(int)
    cleaned["inversion"] = df.get("inversion", pd.Series(dtype=object)).map(to_decimal)
    cleaned["ingresos"] = df.get("ingresos", pd.Series(dtype=object)).map(to_decimal)

    # ACOS and ROAS are recomputed from spend and revenue rather than read
    # from the report columns: this keeps the same rule when aggregating by
    # campaign, where per-ad percentages cannot be averaged.
    spend = cleaned["inversion"].fillna(0)
    revenue = cleaned["ingresos"].fillna(0)
    cleaned["acos"] = (spend / revenue.where(revenue > 0)) * 100
    cleaned["roas"] = revenue / spend.where(spend > 0)

    cleaned = cleaned[cleaned["campana"].notna() & (cleaned["campana"] != "nan")].copy()

    # v2 schema tag. Every row that comes from the Excel path is stamped
    # 'excel'; the API path stamps 'api'. The validator on the save step
    # rejects a snapshot that lacks it.
    cleaned["origen"] = "excel"

    dates_from = cleaned["desde"].dropna()
    dates_to = cleaned["hasta"].dropna()
    return AdsReport(
        datos=cleaned.reset_index(drop=True),
        desde=dates_from.min() if len(dates_from) else None,
        hasta=dates_to.max() if len(dates_to) else None,
    )

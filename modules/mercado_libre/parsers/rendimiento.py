"""Parser for the Mercado Libre listing performance report.

File structure: the first 5 rows are a descriptive header (row 2 carries
the period in prose) and the column names sit on row 5. Data starts at
row 6.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .common import (extract_period, normalize_mla, normalize_text,
                     to_decimal, to_int)

_HEADER_ROW = 5
_PERIOD_ROW = 2

_REQUIRED_COLUMNS = {
    "id de la publicacion", "publicacion", "estado actual",
    "visitas unicas", "cantidad de ventas", "unidades vendidas",
}


@dataclass
class PerformanceReport:
    """Parse result: the data plus the period it covers."""
    datos: pd.DataFrame
    desde: date
    hasta: date

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1


class FormatError(Exception):
    """The file is not shaped like a performance report."""


def parse(file) -> PerformanceReport:
    raw = pd.read_excel(file, sheet_name=0, header=None)

    period = extract_period(raw.iloc[_PERIOD_ROW, 0]) if len(raw) > _PERIOD_ROW else None
    if period is None:
        raise FormatError(
            "No se pudo leer el período del reporte. Verificá que sea el export "
            "de 'Métricas del rendimiento de tus publicaciones' sin modificar."
        )
    from_date, to_date = period

    file.seek(0) if hasattr(file, "seek") else None
    df = pd.read_excel(file, sheet_name=0, header=_HEADER_ROW)
    df.columns = [normalize_text(c) for c in df.columns]

    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise FormatError(
            "Al reporte le faltan columnas esperadas: "
            + ", ".join(sorted(missing))
            + ". Puede que Mercado Libre haya cambiado el formato del export."
        )

    cleaned = pd.DataFrame()
    cleaned["mla"] = df["id de la publicacion"].map(normalize_mla)
    cleaned["titulo"] = df["publicacion"].astype(str).str.strip()
    cleaned["estado"] = df["estado actual"].map(normalize_text)
    cleaned["variante"] = df.get("variante", pd.Series(dtype=object))
    cleaned["sku"] = df.get("sku", pd.Series(dtype=object))
    cleaned["visitas"] = df["visitas unicas"].map(to_int)
    cleaned["ventas"] = df["cantidad de ventas"].map(to_int)
    cleaned["unidades"] = df["unidades vendidas"].map(to_int)

    if "ventas brutas (ars)" in df.columns:
        cleaned["facturacion"] = df["ventas brutas (ars)"].map(to_decimal)
    else:
        cleaned["facturacion"] = None

    cleaned = cleaned[cleaned["mla"].notna()].copy()

    # The report has one row per variant. Tracking is defined at listing
    # level, so we aggregate variants before any calculation.
    aggregated = (
        cleaned.groupby("mla", as_index=False)
        .agg(
            titulo=("titulo", "first"),
            estado=("estado", "first"),
            visitas=("visitas", "sum"),
            ventas=("ventas", "sum"),
            unidades=("unidades", "sum"),
            facturacion=("facturacion", "sum"),
            variantes=("mla", "size"),
        )
    )

    # Conversion is recomputed rather than averaging the report column:
    # averaging percentages across variants with different traffic yields
    # a figure that does not represent the listing.
    valid_visits = aggregated["visitas"].where(aggregated["visitas"] > 0)
    aggregated["conversion"] = aggregated["ventas"] / valid_visits

    aggregated["desde"] = from_date
    aggregated["hasta"] = to_date
    # Schema v2 introduced the "origen" column so a single Parquet can carry
    # rows coming from the Meli API and rows coming from the AM's Excel side
    # by side. The parser handles the Excel side, so it always stamps
    # "excel" here — api_bridge stamps "api" for rows it builds from
    # Postgres. Downstream can filter or blend without loading two files.
    aggregated["origen"] = "excel"

    return PerformanceReport(datos=aggregated, desde=from_date, hasta=to_date)

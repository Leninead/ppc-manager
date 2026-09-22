"""The Análisis de Funnel agent's payload, built from what the module already computed, without Streamlit."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids
from ai.agents.funnel.chat_document import row_item
from ai.agents.funnel.context import ROW_PREFIX, FunnelData, records_of
from core.funnel.coverage import (
    ACTIVE_CAMPAIGN_COLUMN,
    CAMPAIGN_STATE_COLUMN,
    CVR_COLUMN,
    SOURCE_CAMPAIGN_COLUMN,
    SUGGESTED_MATCH_COLUMN,
    FunnelCoverage,
    OrdersAndSales,
    acos_column,
    campaign_column,
    orders_and_sales,
)

ANALYSIS_MODULE = "funnel"
GROUP_HARVEST = "harvest"
GROUP_GAP = "brecha"
GROUP_IDLE = "sin_trafico"


@dataclass(frozen=True)
class FunnelAnalysisInput:
    """The agent payload plus the rows its row_ids point to; `data` is None when there is nothing to judge."""

    data: FunnelData | None
    records: list


def build_analysis_input(coverage: FunnelCoverage, harvest: pd.DataFrame, suggested: pd.DataFrame, *,
                         account_label: str, period_label: str, currency_code: str, attribution_days: int,
                         min_orders: int, match_type: str, lang: str) -> FunnelAnalysisInput:
    columns = coverage.columns
    harvest_rows = [_harvest_record(row, columns) for _, row in harvest.iterrows()]
    gap_rows = [_gap_record(row) for _, row in suggested.iterrows()]
    idle_rows = _idle_records(coverage.idle_campaigns)
    if not (harvest_rows or gap_rows or idle_rows):
        return FunnelAnalysisInput(None, [])
    exact = int((harvest[SUGGESTED_MATCH_COLUMN] == "Exact").sum()) if not harvest.empty else 0
    counts = {
        "Campañas de Sponsored Products": len(coverage.campaigns),
        "Campañas activas": len(coverage.active_campaigns),
        "Campañas pausadas": coverage.paused_campaigns,
        **({"Campañas de Sponsored Brands y Display, fuera del cruce": coverage.other_products}
           if coverage.other_products else {}),
        "Filas del search term report de campañas activas": len(coverage.active_terms),
        "Filas del search term report de campañas pausadas o inexistentes": len(coverage.gap_terms),
        **_sold_counts(orders_and_sales(coverage.active_terms, columns), "campañas activas"),
        **_sold_counts(orders_and_sales(coverage.gap_terms, columns), "campañas pausadas o inexistentes"),
        "Search terms sin campaña activa": len(suggested),
        "Campañas activas sin search terms": len(coverage.idle_campaigns),
        "Candidatos a harvest": len(harvest),
        "Candidatos a harvest en Exact": exact,
        "Candidatos a harvest en Phrase": len(harvest) - exact,
    }
    data = FunnelData(account_label=account_label, period_label=period_label, currency_code=currency_code,
                      attribution_days=attribution_days, matched_by=coverage.matched_by, min_orders=min_orders,
                      match_type=match_type, counts=counts, harvest=harvest_rows, gaps=gap_rows, idle=idle_rows,
                      idioma=lang)
    return FunnelAnalysisInput(data, records_of(data))


def funnel_row_labels(records: list) -> dict[str, str]:
    """row_id -> the term or campaign behind it, to annotate the ids the synthesis and the chat cite (F03)."""
    return {row_id: row_item(record) for row_id, record in zip(make_ids(ROW_PREFIX, len(records)), records)}


def _harvest_record(row: pd.Series, columns: dict) -> dict:
    return {
        "grupo": GROUP_HARVEST,
        "termino": str(row[columns["search_term"]]).strip(),
        "campanas": row[SOURCE_CAMPAIGN_COLUMN],
        "en_campana_activa": bool(row[ACTIVE_CAMPAIGN_COLUMN]),
        "clicks": _plain(row.get(columns["clicks"])),
        "orders": _plain(row.get(columns["orders"])),
        "sales": _plain(row.get(columns["sales"])),
        "spend": _plain(row.get(columns["spend"])),
        "acos": _plain(row.get(acos_column(columns))),
        "cvr": _plain(row.get(CVR_COLUMN)),
        "match_sugerido": row[SUGGESTED_MATCH_COLUMN],
    }


def _sold_counts(sold: OrdersAndSales, campaigns: str) -> dict:
    """The Parámetros lines for what the search terms of `campaigns` sold, leaving out what the report lacks."""
    return {label: value for label, value in ((f"Órdenes de search terms en {campaigns}", sold.orders),
                                              (f"Ventas de search terms en {campaigns}", sold.sales))
            if value is not None}


def _gap_record(row: pd.Series) -> dict:
    return {
        "grupo": GROUP_GAP,
        "termino": row["Customer Search Term"],
        "campana_origen": str(row["Campaña origen (inactiva)"]).strip(),
        "estado_campana": row[CAMPAIGN_STATE_COLUMN],
        "clicks": _plain(row["Clicks"]),
        "spend": _plain(row["Spend"]),
        "orders": _plain(row["Orders"]),
        "sales": _plain(row["Sales"]),
        "nombre_sugerido": row["Nombre sugerido"],
    }


def _idle_records(idle: pd.DataFrame) -> list[dict]:
    name = campaign_column(idle, "campaign name")
    numbers = {}
    for key, header in (("presupuesto", "campaign budget amount"), ("impressions", "impressions"),
                        ("clicks", "clicks"), ("spend", "total cost"), ("orders", "purchases"), ("sales", "sales")):
        column = campaign_column(idle, header)
        numbers[key] = (pd.to_numeric(idle[column], errors="coerce") if column
                        else pd.Series(float("nan"), index=idle.index))
    records = [{"grupo": GROUP_IDLE, "campana": str(campaign).strip(),
                **{key: _plain(values[index]) for key, values in numbers.items()}}
               for index, campaign in idle[name].items()]
    # The largest budget first: that is the money an idle campaign keeps waiting for traffic.
    return sorted(records, key=lambda record: -(record["presupuesto"] or 0))


def _plain(value):
    """JSON-safe: numpy numbers become Python ones, and a missing value is None, never NaN."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number):
        return None
    return int(number) if number.is_integer() else round(number, 2)

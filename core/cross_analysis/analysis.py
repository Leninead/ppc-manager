"""The Análisis Cruzado agent's payload, built from the plan and the ASIN summary the module already computed.

No Streamlit: the page and the tests build the same payload, so the same data always fingerprints the same.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids
from ai.agents.cross_analysis.chat_document import row_item
from ai.agents.cross_analysis.context import ROW_PREFIX, CrossData, records_of
from core.cross_analysis.action_plan import (
    ACTION,
    ACTION_ADD,
    ACTION_ASIN,
    ACTION_BRAND_NO_DATA,
    ACTION_BRAND_OK,
    ACTION_CONQUEST,
    ACTION_DEFEND,
    ACTION_DO_NOT_ATTACK,
    ACTION_INVESTIGATE,
    ACTION_LOWER_BID,
    ACTION_MONITOR,
    ACTION_SCALE,
    BRAND_CVR,
    BRAND_IMPRESSIONS,
    BRAND_PURCHASE_SHARE,
    BRAND_PURCHASES,
    BRAND_QUERY,
    CAMPAIGN_COUNT,
    FUNNEL_DIAGNOSIS,
    IN_SEARCH_TERMS,
    IN_SEARCH_TERMS_YES,
    MARKET_CLICKS,
    MARKET_CVR,
    MARKET_IMPRESSIONS,
    MARKET_PURCHASES,
    QUERY,
    QUERY_TYPE,
    TERM_ACOS,
    TERM_ORDERS,
    TERM_SALES,
    TERM_SPEND,
)
from core.cross_analysis.asin_summary import (
    ACOS,
    AD_SALES,
    AD_SPEND,
    ASIN,
    BR_SALES,
    BR_SESSIONS,
    CVR,
    GROUPED,
    ORDERS,
    PRODUCT,
)
from core.cross_analysis.ranking_guards import ALREADY_EXACT, NOT_NEGATABLE, ORIGIN, RANKING_KEYWORD
from core.search_term.frame import CAMPAIGN_NAME, SEARCH_TERM

ANALYSIS_MODULE = "cross_analysis"

ACTION_NAMES = {
    ACTION_SCALE: "ESCALAR", ACTION_ADD: "AGREGAR", ACTION_DEFEND: "DEFENDER", ACTION_LOWER_BID: "BAJAR BID",
    ACTION_INVESTIGATE: "INVESTIGAR", ACTION_CONQUEST: "CONQUEST", ACTION_DO_NOT_ATTACK: "NO ATACAR",
    ACTION_BRAND_NO_DATA: "SIN DATA", ACTION_BRAND_OK: "BRAND PURE OK", ACTION_ASIN: "ASIN",
    ACTION_MONITOR: "MONITOREAR",
}
# The order the AM works the plan in: what the module exports, then what needs a decision, then the rest.
ACTION_ORDER = (ACTION_SCALE, ACTION_ADD, ACTION_DEFEND, ACTION_LOWER_BID, ACTION_INVESTIGATE, ACTION_CONQUEST,
                ACTION_DO_NOT_ATTACK, ACTION_BRAND_NO_DATA, ACTION_BRAND_OK, ACTION_ASIN, ACTION_MONITOR)


@dataclass(frozen=True)
class CrossAnalysisInput:
    """The agent payload plus the queries its row_ids point to; `data` is None when there is nothing to judge."""

    data: CrossData | None
    records: list


def build_analysis_input(plan: pd.DataFrame, asin_rows: pd.DataFrame, *, account: str, period: str, currency: str,
                         brand: str, exact_source: str, asin_source: str, parameters: dict, counts: dict,
                         lang: str, from_bulk_file: bool = False) -> CrossAnalysisInput:
    if plan.empty:
        return CrossAnalysisInput(None, [])
    data = CrossData(
        account=account, period=period, currency=currency, brand=brand, exact_source=exact_source,
        asin_source=asin_source, parameters=parameters, counts=counts,
        queries=[_query_record(row) for row in _work_order(plan).to_dict("records")],
        asins=[_asin_record(row) for row in asin_rows.to_dict("records")],
        idioma=lang, from_bulk_file=from_bulk_file,
    )
    return CrossAnalysisInput(data, records_of(data))


def plan_counts(plan: pd.DataFrame, sqp: pd.DataFrame, search_terms: pd.DataFrame) -> dict:
    """The module's figures over the whole plan and report, so the agent never adds rows up."""
    report_terms = set(search_terms[SEARCH_TERM].dropna().astype(str).str.lower().str.strip())
    queries = set(plan[QUERY].dropna().astype(str).str.lower().str.strip())
    counts = {
        "Queries del SQP, sin repetir": len(plan),
        "Queries que también son search terms con clicks": len(queries & report_terms),
        "Queries del SQP sin ningún search term": len(queries - report_terms),
        "Search terms con clicks que no están en el SQP": len(report_terms - queries),
    }
    for action in ACTION_ORDER:
        with_action = int((plan[ACTION] == action).sum())
        if with_action:
            counts[f"Queries con acción {ACTION_NAMES[action]}"] = with_action
    if ALREADY_EXACT in plan.columns and plan[ALREADY_EXACT].notna().all():
        counts["Queries que ya existen como keyword Exact habilitada"] = int(plan[ALREADY_EXACT].eq(True).sum())
    brand_share = brand_impression_share(sqp)
    if brand_share is not None:
        counts["Share de impresiones de la marca en el SQP (%)"] = round(brand_share, 1)
    return counts


def brand_impression_share(sqp: pd.DataFrame) -> float | None:
    """The brand's impressions over the market's in the whole SQP, in %; None when the SQP lacks either count."""
    if MARKET_IMPRESSIONS not in sqp.columns or BRAND_IMPRESSIONS not in sqp.columns:
        return None
    market = pd.to_numeric(sqp[MARKET_IMPRESSIONS], errors="coerce").fillna(0).sum()
    brand = pd.to_numeric(sqp[BRAND_IMPRESSIONS], errors="coerce").fillna(0).sum()
    return float(brand / market * 100) if market > 0 else None


def cross_row_labels(records: list) -> dict[str, str]:
    """row_id -> the query behind it, to annotate the ids the synthesis and the chat cite (X03)."""
    return {row_id: row_item(record) for row_id, record in zip(make_ids(ROW_PREFIX, len(records)), records)}


def _work_order(plan: pd.DataFrame) -> pd.DataFrame:
    rank = plan[ACTION].map({action: position for position, action in enumerate(ACTION_ORDER)})
    purchases = (pd.to_numeric(plan[MARKET_PURCHASES], errors="coerce").fillna(0) if MARKET_PURCHASES in plan.columns
                 else pd.Series(0, index=plan.index))
    return (plan.assign(_rank=rank.fillna(len(ACTION_ORDER)), _purchases=purchases,
                        _query=plan[QUERY].astype(str).str.strip())
            .sort_values(["_rank", "_purchases", "_query"], ascending=[True, False, True], kind="mergesort"))


def _query_record(row: dict) -> dict:
    return {
        "consulta": str(row[QUERY]).strip(),
        "accion": ACTION_NAMES.get(row[ACTION], row[ACTION]),
        "tipo": "marca" if row.get(QUERY_TYPE) == BRAND_QUERY else "genérica",
        "en_str": "sí" if row.get(IN_SEARCH_TERMS) == IN_SEARCH_TERMS_YES else "no",
        "compras_mercado": _plain(row.get(MARKET_PURCHASES)),
        "compras_marca": _plain(row.get(BRAND_PURCHASES)),
        "share_compras_marca": _plain(row.get(BRAND_PURCHASE_SHARE)),
        "impresiones_mercado": _plain(row.get(MARKET_IMPRESSIONS)),
        "clicks_mercado": _plain(row.get(MARKET_CLICKS)),
        "cvr_mercado": _plain(row.get(MARKET_CVR)),
        "cvr_marca": _plain(row.get(BRAND_CVR)),
        "diagnostico_funnel": _text(row.get(FUNNEL_DIAGNOSIS)),
        "gasto": _plain(row.get(TERM_SPEND)),
        "ventas": _plain(row.get(TERM_SALES)),
        "ordenes": _plain(row.get(TERM_ORDERS)),
        "acos": _plain(_rounded(row.get(TERM_ACOS))),
        "campana": _text(row.get(CAMPAIGN_NAME)),
        "campanas": _plain(row.get(CAMPAIGN_COUNT)),
        "origen": _text(row.get(ORIGIN)),
        "no_negativizable": _yes_no(row.get(NOT_NEGATABLE)),
        "ranking_kw": _yes_no(row.get(RANKING_KEYWORD)),
        "ya_en_exact": _yes_no(row.get(ALREADY_EXACT), unknown="sin dato"),
    }


def _asin_record(row: dict) -> dict:
    asin = str(row[ASIN])
    product = _text(row.get(PRODUCT))
    return {
        "asin": asin,
        "producto": product if product != asin else "",
        "agrupa": _text(row.get(GROUPED)),
        "gasto": _plain(row.get(AD_SPEND)),
        "ventas": _plain(row.get(AD_SALES)),
        "acos": _plain(row.get(ACOS)),
        "ordenes": _plain(row.get(ORDERS)),
        "cvr": _plain(row.get(CVR)),
        "sesiones_br": _plain(row.get(BR_SESSIONS)),
        "ventas_br": _plain(row.get(BR_SALES)),
    }


def _yes_no(value, *, unknown: str = "no") -> str:
    if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)):
        return unknown
    return "sí" if bool(value) else "no"


def _rounded(value):
    return round(float(value), 1) if _plain(value) is not None else None


def _text(value) -> str:
    return "" if value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value)) else str(value)


def _plain(value):
    """JSON-safe: numpy numbers become Python ones, and a missing value is None, never NaN."""
    if value is None or value is pd.NA:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number):
        return None
    return int(number) if number.is_integer() else round(number, 2)

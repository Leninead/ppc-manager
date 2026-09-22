"""The PPC Insights agent's payload and its parameters, without Streamlit.

The page and the analysis worker both build it from here: the same data and the same parameters
must give the same digest wherever it runs, or the analysis the worker stored is never found.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ai.agents.ppc_insights.context import ASIN_PREFIX, MAX_ASINS, InsightsData
from core.ppc_insights.asin_health import (
    BLEEDER_MIN_SPEND,
    BLEEDERS_KEPT,
    MAX_POINTS,
    NEUTRAL_POINTS,
    InsightsAnalysisParams,
    analyze_asins,
    resolve_asins,
)

ANALYSIS_MODULE = "ppc_insights"
CANONICAL_LANG = "es"
# The window the picker opens on: an analysis asked for from the page covers what the AM sees.
CANONICAL_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 60


@dataclass(frozen=True)
class InsightsAnalysisInput:
    """The agent payload plus the rows its row_ids point to."""

    data: InsightsData | None
    records: list


def canonical_analysis_window(data_from: date | None, data_through: date) -> tuple[date, date]:
    earliest = data_from or data_through - timedelta(days=MAX_WINDOW_DAYS - 1)
    return max(earliest, data_through - timedelta(days=CANONICAL_WINDOW_DAYS - 1)), data_through


def build_analysis_input(frame, *, params: InsightsAnalysisParams, account_label: str, period_label: str,
                         currency_code: str, lang: str = CANONICAL_LANG, ad_group_asins: dict | None = None,
                         sqp_df=None, br_df=None, camp_df=None) -> InsightsAnalysisInput:
    """The agent's payload from a Search Term Report frame and the optional files the AM loaded."""
    if frame is None or frame.empty:
        return InsightsAnalysisInput(None, [])
    resolved = resolve_asins(frame.copy(), ad_group_asins)
    asin_data = analyze_asins(resolved.frame.copy(), _copy(sqp_df), _copy(br_df), _copy(camp_df),
                              params.target_acos, resolved.column)
    if not asin_data:
        return InsightsAnalysisInput(None, [])

    ordered = sorted(asin_data, key=lambda asin: (-asin_data[asin]["spend"], str(asin)))
    sources = {"sqp": sqp_df is not None, "br": br_df is not None, "campaigns": camp_df is not None}
    records = [_record(asin, asin_data[asin], sources, resolved.grouped_asins.get(asin))
               for asin in ordered[:MAX_ASINS]]
    return InsightsAnalysisInput(
        InsightsData(
            account_label=account_label,
            period_label=period_label,
            currency_code=currency_code,
            target_acos=params.target_acos,
            price=params.price,
            asin_source=resolved.source,
            asin_spend_share=resolved.spend_share,
            sources=sources,
            # The SQP shares are the brand's, identical in every row: any row carries them.
            brand_sqp=_brand_sqp(asin_data[ordered[0]]) if sources["sqp"] else None,
            score_scale={part: (MAX_POINTS[part], NEUTRAL_POINTS[part]) for part in MAX_POINTS},
            wasted_spend_rule=(BLEEDER_MIN_SPEND, BLEEDERS_KEPT),
            total_asins=len(asin_data),
            asins=records,
            idioma=lang,
        ),
        records,
    )


def insights_row_labels(records: list) -> dict[str, str]:
    """row_id -> ASIN, for the ids the AI cites in its prose."""
    return {f"{ASIN_PREFIX}{index:02d}": str(record.get("asin", "")) for index, record in enumerate(records, 1)}


def _record(asin, metrics: dict, sources: dict, grouped_asins: int | None) -> dict:
    parts = metrics["health_parts"]
    record = {
        "asin": str(asin),
        "health_score": metrics["health_score"],
        **{f"pts_{part}": round(float(points), 1) for part, points in parts.items()},
        "spend": round(metrics["spend"], 2),
        "sales": round(metrics["sales"], 2),
        "orders": int(metrics["orders"]),
        "clicks": int(metrics["clicks"]),
        "acos": _rounded(metrics["acos"]),
        "cvr": _rounded(metrics["cvr"]),
        "gasto_sin_venta": round(metrics["wasted_spend"], 2),
        "terminos_sin_venta": int(len(metrics["bleeders"])),
        "top_termino": _top_term(metrics["top_kws"]),
    }
    if sources["br"]:
        record.update(sessions=_rounded(metrics["sessions"], 0), buybox=_rounded(metrics["buybox"]),
                      cvr_br=_rounded(_br_cvr(metrics)))
    if sources["campaigns"]:
        funnel = metrics["funnel_complete"]
        record.update(campanas=metrics["n_campaigns"], tipos_campana=metrics["campaign_types"] or "",
                      funnel="" if funnel is None else ("completo" if funnel else "parcial"))
    if grouped_asins:
        record["asins_agrupados"] = int(grouped_asins)
    return record


def _brand_sqp(metrics: dict) -> dict | None:
    """None when the SQP had no brand columns to measure a share with."""
    if metrics["imp_share"] is None:
        return None
    return {"imp_share": _rounded(metrics["imp_share"]), "purchase_share": _rounded(metrics["purchase_share"]),
            "sqp_gaps": metrics["sqp_gaps"]}


def _top_term(top_terms) -> str:
    if top_terms is None or top_terms.empty or "Search Term" not in top_terms.columns:
        return ""
    return str(top_terms["Search Term"].iloc[0])


def _br_cvr(metrics: dict):
    sessions, units = metrics["sessions"], metrics["br_units"]
    return units / sessions * 100 if units is not None and sessions else None


def _rounded(value, digits: int = 1):
    return None if value is None else round(float(value), digits)


def _copy(frame):
    return None if frame is None else frame.copy()

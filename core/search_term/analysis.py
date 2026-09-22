"""What the STR agent analyzes, built from a search term frame and the account's parameters.

M2 and the analysis worker both call build_analysis_input, so the same data and parameters always
give the same payload, and therefore the same input digest. No Streamlit here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from ai.agents.str.context import StrData
from core.currency_format import money
from core.search_term.candidates import (
    StrAnalysisParams,
    clicks_threshold_for,
    harvest_candidate_rows,
    mark_already_exact,
    measured_cvr,
    negative_candidate_rows,
    sorted_harvest,
)
from core.search_term.negatives import NegativeCandidate, evaluate_candidates

ANALYSIS_MODULE = "str"
CANONICAL_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 60
CANONICAL_LANG = "es"
LANGS = ("es", "en")

# Capped so the model answers in minutes.
AI_NEGATIVE_ROWS = 120
AI_HARVEST_ROWS = 60
AI_PRIORITIES = ("Alta", "Media")

BLOCKED_NO_CANDIDATES = "no_candidates"
BLOCKED_NO_SEARCH_TERMS = "no_search_terms"

_NEGATIVE_SORT = {"Alta": 0, "Media": 1, "Revisar": 2}


@dataclass(frozen=True)
class StrAnalysisInput:
    """The agent payload plus the rows its row ids point to; `blocked_reason` is set when there is nothing to send."""

    data: StrData | None
    negative_records: list[dict]
    harvest_records: list[dict]
    clicks_threshold: int
    spend_threshold: float
    blocked_reason: str = ""


def canonical_analysis_window(data_from: date | None, data_through: date) -> tuple[date, date]:
    """The period M2 opens on: the window the worker analyzes on its own.

    It must track the picker's default period. If the two drift apart, what the AM sees on screen
    never matches a stored analysis and every request pays for a new one.
    """
    earliest = data_from or data_through - timedelta(days=MAX_WINDOW_DAYS - 1)
    return max(earliest, data_through - timedelta(days=CANONICAL_WINDOW_DAYS - 1)), data_through


def account_kpis(frame: pd.DataFrame, currency_code: str) -> dict:
    """The KPI document the agent reads: the tab 1 figures, with no date and no slider in it."""
    total_spend = frame["_spend"].sum()
    total_sales = frame["_sales"].sum()
    total_clicks = frame["_clicks"].sum()
    total_imps = frame["_imps"].sum()
    total_orders = frame["_orders"].sum()
    waste_spend = frame.loc[frame["_sales"] == 0, "_spend"].sum()
    rows_with_sales = (frame["_sales"] > 0).sum()
    return {
        "Total Spend": money(total_spend, currency_code),
        "Total Sales": money(total_sales, currency_code),
        "ACoS": f"{(total_spend / total_sales * 100) if total_sales > 0 else 0:.1f}%",
        "ROAS": f"{(total_sales / total_spend) if total_spend > 0 else 0:.2f}x",
        "Impressions": f"{total_imps:,.0f}",
        "Clicks": f"{total_clicks:,.0f}",
        "CTR": f"{(total_clicks / total_imps * 100) if total_imps > 0 else 0:.2f}%",
        "CVR": f"{(total_orders / total_clicks * 100) if total_clicks > 0 else 0:.2f}%",
        "CPC": money((total_spend / total_clicks) if total_clicks > 0 else 0, currency_code),
        "Orders": f"{total_orders:,.0f}",
        "% Waste": f"{(waste_spend / total_spend * 100) if total_spend > 0 else 0:.1f}%",
        "% Con Ventas": f"{(rows_with_sales / len(frame) * 100) if len(frame) > 0 else 0:.1f}%",
    }


def campaign_totals(frame: pd.DataFrame, cols: dict) -> list[dict]:
    """Per-campaign aggregate, the one tab 5 shows, ranked by spend (or clicks when there is no cost column)."""
    campaign_column = cols["campaign"]
    if not campaign_column or campaign_column not in frame.columns:
        return []
    totals = frame.groupby(campaign_column).agg(
        Impressions=("_imps", "sum"), Clicks=("_clicks", "sum"), Spend=("_spend", "sum"),
        Sales=("_sales", "sum"), Orders=("_orders", "sum"),
    ).reset_index().rename(columns={campaign_column: "Campaign"})
    totals["ACoS"] = (totals["Spend"] / totals["Sales"].replace(0, float("nan")) * 100).fillna(0).round(1)
    # Without a cost column, ranking by Spend is meaningless (all zeros) and can drop the worst bleeders.
    rank_column = "Spend" if cols["spend"] else "Clicks"
    return totals.sort_values(rank_column, ascending=False, kind="mergesort").round(2).to_dict("records")


def build_analysis_input(frame: pd.DataFrame, cols: dict, params: StrAnalysisParams, *, currency_code: str,
                         lang: str, candidates: list[NegativeCandidate] | None = None,
                         existing_exact_terms=None) -> StrAnalysisInput:
    """The payload for `frame` (with metric columns) under `params`.

    `candidates` lets M2 reuse the ones tab 2 already evaluated with the same thresholds.
    `existing_exact_terms` comes from a manual Campaign CSV, so only file sources pass it.
    """
    total_clicks, total_orders = frame["_clicks"].sum(), frame["_orders"].sum()
    clicks_threshold = clicks_threshold_for(total_clicks, total_orders)
    spend_threshold = float("inf") if params.price is None else params.price * 0.50
    if not cols["search_term"]:
        return StrAnalysisInput(None, [], [], clicks_threshold, spend_threshold, BLOCKED_NO_SEARCH_TERMS)

    if candidates is None:
        candidates = evaluate_candidates(frame, cols, clicks_threshold=clicks_threshold,
                                         spend_threshold=spend_threshold)
    # evaluate_candidates already sorts by priority, then spend.
    negative_records = [row for row in negative_candidate_rows(candidates)
                        if row["Prioridad"] in AI_PRIORITIES][:AI_NEGATIVE_ROWS]
    harvest = sorted_harvest(harvest_candidate_rows(frame, cols, min_clicks=params.harvest_min_clicks,
                                                    price=params.harvest_price,
                                                    target_acos=params.harvest_target_acos))
    if existing_exact_terms is not None and not harvest.empty:
        harvest = mark_already_exact(harvest, existing_exact_terms)
    harvest_records = harvest.head(AI_HARVEST_ROWS).to_dict("records")
    if not negative_records and not harvest_records:
        return StrAnalysisInput(None, [], [], clicks_threshold, spend_threshold, BLOCKED_NO_CANDIDATES)

    data = StrData(
        cliente="no declarado",
        brand_terms=list(params.brand_terms),
        target_acos=float(params.target_acos),
        precio=params.price,
        # The measured CVR, never the reference value that only sets the Rule 2 threshold.
        cvr=float(measured_cvr(total_clicks, total_orders)),
        umbral_clicks=int(clicks_threshold),
        umbral_spend=float(spend_threshold),
        harvest_target_acos=float(params.harvest_target_acos),
        harvest_precio=params.harvest_price,
        kpis=account_kpis(frame, currency_code),
        campanas=campaign_totals(frame, cols),
        negativos=negative_records,
        harvest=harvest_records,
        idioma=lang,
        cost_detected=bool(cols["spend"]),
        currency_code=currency_code,
    )
    return StrAnalysisInput(data, negative_records, harvest_records, clicks_threshold, spend_threshold)



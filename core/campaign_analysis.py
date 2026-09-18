"""M6's analysis payload and window, without Streamlit.

The page and the analysis worker both build it, so the same campaigns and the same parameters give
the same fingerprint wherever it runs: that is how the page finds the analysis the worker stored.
The rules themselves live in core/amazon_ads/campaign_analyzer.py, which the MCP server also reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from ai.agents.bulk_campaigns.context import CAMPAIGN_PREFIX, MAX_CAMPAIGNS, CampaignData
from core.amazon_ads.campaign_analyzer import (
    ANALYSIS_MODULE,
    DIAGNOSIS_COLUMN,
    OK,
    PAUSE,
    SIGNALS_COLUMN,
    CampaignAnalyzerParams,
    analyze,
    diagnosis_name,
    missing_performance_columns,
    provisional_days,
)
from core.amazon_ads.campaign_provider import BID_STRATEGY, BUDGET_AMOUNT, CAMPAIGN_ID, CAMPAIGN_NAME, PORTFOLIO_NAME

__all__ = ["ANALYSIS_MODULE", "CANONICAL_LANG", "BulkCampaignsInput", "build_analysis_input",
           "campaign_row_labels", "canonical_analysis_window"]

CANONICAL_LANG = "es"
# The window the picker opens with: if they differ, what the AM sees never finds its analysis.
CANONICAL_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 60


def canonical_analysis_window(data_from: date | None, data_through: date) -> tuple[date, date]:
    earliest = data_from or data_through - timedelta(days=MAX_WINDOW_DAYS - 1)
    return max(earliest, data_through - timedelta(days=CANONICAL_WINDOW_DAYS - 1)), data_through


@dataclass(frozen=True)
class BulkCampaignsInput:
    """The agent's payload plus the rows its row_ids point to."""

    data: CampaignData | None
    records: list


def build_analysis_input(frame: pd.DataFrame, *, signal_inputs: pd.DataFrame | None,
                         params: CampaignAnalyzerParams, account_label: str, period_label: str,
                         currency_code: str, attribution_days: int, window_start: date, window_end: date,
                         lang: str = CANONICAL_LANG) -> BulkCampaignsInput:
    """The payload the agent reads, from the Campaign Manager frame and its signal inputs."""
    if frame.empty or missing_performance_columns(frame):
        return BulkCampaignsInput(None, [])
    analyzer, campaigns = analyze(frame, signal_inputs, params, window_start=window_start, window_end=window_end)
    if campaigns.empty:
        return BulkCampaignsInput(None, [])
    has_signals = signal_inputs is not None
    records = campaign_records(campaigns, has_impressions=analyzer.has_impressions, has_signals=has_signals,
                               keep=MAX_CAMPAIGNS)
    counts = campaigns[DIAGNOSIS_COLUMN].map(diagnosis_name).value_counts()
    return BulkCampaignsInput(
        CampaignData(
            account_label=account_label,
            period_label=period_label,
            currency_code=currency_code,
            attribution_days=int(attribution_days),
            target_acos=float(params.target_acos),
            spend_to_pause=float(params.spend_to_pause),
            min_orders_to_scale=int(params.min_orders_to_scale),
            enabled_campaigns=len(campaigns),
            counts={str(name): int(count) for name, count in counts.items()},
            pause_spend=round(float(campaigns.loc[campaigns[DIAGNOSIS_COLUMN] == PAUSE, "_spend"].sum()), 2),
            provisional_days=[day.isoformat() for day in provisional_days(window_start, window_end)],
            has_impressions=analyzer.has_impressions,
            has_signals=has_signals,
            campaigns=records,
            idioma=lang,
        ),
        records,
    )


def campaign_records(campaigns: pd.DataFrame, *, has_impressions: bool, has_signals: bool, keep: int) -> list[dict]:
    """The campaigns the agent reads, in native types: flagged first (a diagnosis other than OK or any
    signal), then by spend, with name and id breaking ties so the order never depends on the database's."""
    flagged = (campaigns[DIAGNOSIS_COLUMN] != OK) | (campaigns[SIGNALS_COLUMN] != "")
    ordered = campaigns.assign(
        _unflagged=~flagged,
        _name=campaigns[CAMPAIGN_NAME].astype(str) if CAMPAIGN_NAME in campaigns.columns else "",
        _id=campaigns[CAMPAIGN_ID].astype(str) if CAMPAIGN_ID in campaigns.columns else "",
    ).sort_values(["_unflagged", "_spend", "_name", "_id"], ascending=[True, False, True, True], kind="mergesort")
    return [_record(row, has_impressions, has_signals) for _, row in ordered.head(keep).iterrows()]


def campaign_row_labels(records) -> dict:
    """row_id -> campaign name, to annotate the ids the synthesis and the chat cite (C03)."""
    return {f"{CAMPAIGN_PREFIX}{i + 1:02d}": str(record.get("campaign", "")).strip()
            for i, record in enumerate(records or [])}


def _record(row, has_impressions: bool, has_signals: bool) -> dict:
    spend, sales = round(float(row["_spend"]), 2), round(float(row["_sales"]), 2)
    orders, clicks = int(row["_orders"]), int(row["_clicks"])
    record = {
        "campaign": _text(row.get(CAMPAIGN_NAME)),
        "portfolio": _text(row.get(PORTFOLIO_NAME)),
        "estrategia": _text(row.get(BID_STRATEGY)),
        "presupuesto": _rounded(row.get(BUDGET_AMOUNT), 2),
        "diagnostico": diagnosis_name(row[DIAGNOSIS_COLUMN]),
        "senales": str(row.get(SIGNALS_COLUMN) or ""),
        "spend": spend,
        "sales": sales,
        "orders": orders,
        "clicks": clicks,
        # An ACoS, a CPC or a CTR without its base is not zero: the agent reads the empty cell as "none".
        "acos": round(float(row["_acos"]), 1) if sales > 0 else None,
        "cpc": round(spend / clicks, 2) if clicks > 0 else None,
    }
    if has_impressions:
        impressions = int(row["_impr"])
        record["impressions"] = impressions
        record["ctr"] = round(clicks / impressions * 100, 2) if impressions > 0 else None
    if has_signals:
        record["dias_con_impresiones"] = _whole(row.get("_days_with_impressions"))
        record["dias_tope_presupuesto"] = _whole(row.get("_budget_capped_days"))
        record["tos_is"] = _rounded(row.get("_top_of_search_is"), 2)
        record["dias_desde_inicio"] = _whole(row.get("_days_live"))
    return record


def _text(value) -> str:
    return "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value).strip()


def _rounded(value, digits: int) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), digits)


def _whole(value) -> int | None:
    return None if value is None or pd.isna(value) else int(value)

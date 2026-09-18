"""Module-agnostic read API for synced Amazon Ads campaign data.

Reads `campaigns_between` over PostgREST and returns one row per campaign under the column names
of the Campaign Manager export, which is what the campaign-level modules already read. The
universe comes from the campaign entities, so a campaign with no activity in the range is a row
of zeros, never a missing row.
"""
from __future__ import annotations

import dataclasses
import io
import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from core.amazon_ads.report_provider import (
    READ_TIMEOUT_SECONDS,
    SELLER_ATTRIBUTION_DAYS,
    VENDOR_ATTRIBUTION_DAYS,
    ProfileOption,
    ReportReadError,
    _attribution_days,
    _numbers,
    _portfolio_label,
    _single_currency,
)
from core.integrations.store import _error_message, _Rest

log = logging.getLogger(__name__)

CAMPAIGNS_RPC = "campaigns_between"
SPONSORED_PRODUCTS = "Sponsored Products"
# Campaign Manager hides archived campaigns unless asked; the AM compares against that view.
ARCHIVED_STATE = "ARCHIVED"

CAMPAIGN_NAME = "Campaign name"
CAMPAIGN_ID = "Campaign ID"
STATE = "State"
TYPE = "Type"
PORTFOLIO_NAME = "Portfolio name"
START_DATE = "Campaign start date"
BID_STRATEGY = "Campaign bid strategy"
BUDGET_AMOUNT = "Campaign budget amount"
IMPRESSIONS = "Impressions"
CLICKS = "Clicks"
CTR = "CTR"
TOTAL_COST = "Total cost"
CPC = "CPC"
PURCHASES = "Purchases"
SALES = "Sales"
ACOS = "ACOS"
ROAS = "ROAS"
FRAME_COLUMNS = (CAMPAIGN_NAME, CAMPAIGN_ID, STATE, TYPE, PORTFOLIO_NAME, START_DATE, BID_STRATEGY,
                 BUDGET_AMOUNT, IMPRESSIONS, CLICKS, CTR, TOTAL_COST, CPC, PURCHASES, SALES, ACOS, ROAS)

_TEXT_FIELDS = ("campaign_id", "name", "state", "targeting_type", "start_date", "budget_type",
                "bidding_strategy", "portfolio_id", "portfolio_name", "currency_code")
_COUNT_FIELDS = ("impressions", "clicks", "purchases_7d", "purchases_14d")
_AMOUNT_FIELDS = ("cost", "sales_7d", "sales_14d")
_RPC_FIELDS = _TEXT_FIELDS + ("budget_amount",) + _COUNT_FIELDS + _AMOUNT_FIELDS
# What the analyzer's signals are computed from (migration 014). Optional: a database without 014
# answers without them, and then the signals are unknown, never zero.
SIGNAL_DAY_FIELDS = ("budget_capped_days", "days_with_impressions")
SIGNAL_SHARE_FIELD = "top_of_search_is"
SIGNAL_COLUMNS = (CAMPAIGN_ID, "start_date", "budget_type", *SIGNAL_DAY_FIELDS, SIGNAL_SHARE_FIELD)
_ATTRIBUTION_FIELDS = {
    SELLER_ATTRIBUTION_DAYS: ("sales_7d", "purchases_7d"),
    VENDOR_ATTRIBUTION_DAYS: ("sales_14d", "purchases_14d"),
}


@dataclass(frozen=True)
class CampaignSource:
    frame: pd.DataFrame
    currency_code: str
    label: str
    profile_id: str
    window_start: date
    window_end: date
    attribution_days: int
    # One row per campaign of `frame`, keyed by Campaign ID; None when the database has no signal columns.
    signal_inputs: pd.DataFrame | None = None


def campaign_sync_view(option: ProfileOption, completed) -> ProfileOption:
    """The profile as the campaign sync sees it: window, day and hour from its last completed request.

    `ads_profile_sync` carries the search-term sync, which says nothing about campaigns; `completed`
    is the last `sp_campaigns` SyncJob that finished well, or None.
    """
    if completed is None:
        return dataclasses.replace(option, data_from=None, data_through=None, refreshed_on=None,
                                   last_success_at=None)
    return dataclasses.replace(option, data_from=completed.window_start, data_through=completed.window_end,
                               refreshed_on=completed.local_day, last_success_at=completed.finished_at)


class CampaignProvider:
    def __init__(self, rest: _Rest):
        self._rest = rest

    def campaigns(self, option: ProfileOption, start: date, end: date) -> CampaignSource:
        """One profile's campaigns with their metrics summed over [start, end]."""
        if end < start:
            raise ValueError(f"campaign range ends before it starts: {start}..{end}")
        try:
            csv_bytes = self._rest.rpc_csv(
                CAMPAIGNS_RPC,
                {"p_profile_id": option.profile_id, "p_from": start.isoformat(), "p_to": end.isoformat()},
                timeout_s=READ_TIMEOUT_SECONDS,
            )
            totals = _read_campaigns(csv_bytes)
        except (requests.RequestException, ValueError) as exc:
            raise ReportReadError(_error_message(exc, "leer las campañas de Amazon Ads")) from exc

        attribution_days = _attribution_days(option.account_type)
        frame = campaign_frame(totals, attribution_days)
        log.info("amazon ads campaigns read: profile %s %s..%s, %d campaigns, %dd attribution",
                 option.profile_id, start, end, len(frame), attribution_days)
        return CampaignSource(
            frame=frame,
            currency_code=option.currency_code or _single_currency(totals),
            label=f"{option.label} · {option.country_code}" if option.country_code else option.label,
            profile_id=option.profile_id,
            window_start=start,
            window_end=end,
            attribution_days=attribution_days,
            signal_inputs=signal_inputs_frame(totals),
        )


def campaign_frame(totals: pd.DataFrame, attribution_days: int) -> pd.DataFrame:
    """The Campaign Manager export shape; ratios are fractions, the way the export writes them."""
    sales_field, purchases_field = _ATTRIBUTION_FIELDS[attribution_days]
    live = _live_campaigns(totals)
    cost, sales, clicks, impressions = live["cost"], live[sales_field], live["clicks"], live["impressions"]
    return pd.DataFrame({
        CAMPAIGN_NAME: live["name"],
        CAMPAIGN_ID: live["campaign_id"],
        STATE: live["state"].str.strip().str.upper(),
        TYPE: SPONSORED_PRODUCTS,
        PORTFOLIO_NAME: [_portfolio_label(portfolio_id, name) for portfolio_id, name
                         in zip(live["portfolio_id"], live["portfolio_name"])],
        START_DATE: live["start_date"],
        BID_STRATEGY: live["bidding_strategy"],
        BUDGET_AMOUNT: live["budget_amount"],
        IMPRESSIONS: impressions,
        CLICKS: clicks,
        CTR: clicks / impressions.where(impressions > 0),
        TOTAL_COST: cost,
        CPC: cost / clicks.where(clicks > 0),
        PURCHASES: live[purchases_field],
        SALES: sales,
        ACOS: cost / sales.where(sales > 0),
        ROAS: sales / cost.where(cost > 0),
    }, columns=list(FRAME_COLUMNS))


def signal_inputs_frame(totals: pd.DataFrame) -> pd.DataFrame | None:
    """The signal inputs of the campaigns `campaign_frame` keeps, in its order; None without migration 014."""
    if any(field not in totals.columns for field in (*SIGNAL_DAY_FIELDS, SIGNAL_SHARE_FIELD)):
        return None
    live = _live_campaigns(totals)
    return pd.DataFrame({
        CAMPAIGN_ID: live["campaign_id"],
        "start_date": pd.to_datetime(live["start_date"].where(live["start_date"].str.strip() != ""),
                                     errors="coerce").dt.date,
        "budget_type": live["budget_type"].str.strip().str.upper(),
        **{field: live[field] for field in SIGNAL_DAY_FIELDS},
        SIGNAL_SHARE_FIELD: live[SIGNAL_SHARE_FIELD],
    }, columns=list(SIGNAL_COLUMNS)).reset_index(drop=True)


def _live_campaigns(totals: pd.DataFrame) -> pd.DataFrame:
    live = totals[totals["state"].str.strip().str.upper() != ARCHIVED_STATE]
    return live.sort_values(["name", "campaign_id"], kind="mergesort").reset_index(drop=True)


def _read_campaigns(csv_bytes: bytes) -> pd.DataFrame:
    """The RPC answer with text fields as str and metrics parsed; raises ValueError on a malformed answer."""
    if csv_bytes.strip():
        # keep_default_na=False: a campaign named "NA" or "null" is text, not a missing value.
        totals = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="utf-8")
    else:
        totals = pd.DataFrame({field: pd.Series(dtype=str) for field in _RPC_FIELDS})
    missing = [field for field in _RPC_FIELDS if field not in totals.columns]
    if missing:
        raise ValueError(f"{CAMPAIGNS_RPC} answered without columns {missing}")
    for field in _TEXT_FIELDS:
        # PostgREST writes text/csv from record_out, which doubles every backslash inside a field.
        totals[field] = totals[field].str.replace("\\\\", "\\", regex=False)
    for field in _COUNT_FIELDS:
        totals[field] = _numbers(totals, field, CAMPAIGNS_RPC).round().astype("int64")
    for field in _AMOUNT_FIELDS:
        totals[field] = _numbers(totals, field, CAMPAIGNS_RPC).astype("float64")
    # A campaign without a budget has no budget, not a budget of zero.
    raw_budget = totals["budget_amount"].str.strip()
    budget = pd.to_numeric(raw_budget, errors="coerce")
    unreadable = budget.isna() & raw_budget.ne("")
    if unreadable.any():
        raise ValueError(f"{CAMPAIGNS_RPC} answered a non-numeric budget_amount: {raw_budget[unreadable].iloc[0]!r}")
    totals["budget_amount"] = budget
    for field in SIGNAL_DAY_FIELDS:
        if field in totals.columns:
            totals[field] = _numbers(totals, field, CAMPAIGNS_RPC).round().astype("int64")
    if SIGNAL_SHARE_FIELD in totals.columns:
        # An empty share is a campaign Amazon gave no share for: unknown, so NaN rather than 0.
        raw_share = totals[SIGNAL_SHARE_FIELD].str.strip()
        share = pd.to_numeric(raw_share, errors="coerce")
        if (share.isna() & raw_share.ne("")).any():
            raise ValueError(f"{CAMPAIGNS_RPC} answered a non-numeric {SIGNAL_SHARE_FIELD}")
        totals[SIGNAL_SHARE_FIELD] = share
    return totals

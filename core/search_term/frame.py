"""Canonical Search Term frame shared by the Amazon Ads provider and the manual file reader.

Column names copy the console export so M2's `_detect_cols` maps them without changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

SOURCE_API = "api"
SOURCE_FILE = "file"

SEARCH_TERM = "Customer Search Term"
CAMPAIGN_NAME = "Campaign Name"
AD_GROUP_NAME = "Ad Group Name"
PORTFOLIO_NAME = "Portfolio name"
MATCH_TYPE = "Match Type"
TARGETING = "Targeting"
IMPRESSIONS = "Impressions"
CLICKS = "Clicks"
SPEND = "Spend"
CTR = "Click-Thru Rate (CTR)"
CPC = "Cost Per Click (CPC)"
ACOS = "Total Advertising Cost of Sales (ACoS)"

# Neither name may contain a fragment M2's `_detect_cols` looks for ("order", "purchases", "portfolio"...).
ANY_WINDOW_PURCHASES = "_any_window_purchase_count"
PORTFOLIO_NAME_MISSING = "_pf_name_missing"

HIDDEN_ID_COLUMNS = ("_campaign_id", "_ad_group_id", "_keyword_id", "_keyword_type", "_origin_match_type",
                     "_campaign_status", "_ad_keyword_status", "_keyword_text", ANY_WINDOW_PURCHASES,
                     PORTFOLIO_NAME_MISSING)

_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


def valid_currency_code(value: object) -> str:
    """The three-letter currency code in upper case, or "" for anything else; the code is later rendered as HTML."""
    if not isinstance(value, str):
        return ""
    code = value.strip().upper()
    return code if _CURRENCY_CODE.fullmatch(code) else ""


def sales_column(attribution_days: int) -> str:
    return f"{attribution_days} Day Total Sales"


def orders_column(attribution_days: int) -> str:
    return f"{attribution_days} Day Total Orders (#)"


def units_column(attribution_days: int) -> str:
    return f"{attribution_days} Day Total Units (#)"


def conversion_rate_column(attribution_days: int) -> str:
    return f"{attribution_days} Day Conversion Rate"


def console_columns(attribution_days: int) -> list[str]:
    # M2 `_detect_cols` keeps the first match, so sales must precede ACoS (whose name also says "sales").
    return [SEARCH_TERM, CAMPAIGN_NAME, AD_GROUP_NAME, PORTFOLIO_NAME, MATCH_TYPE, TARGETING,
            IMPRESSIONS, CLICKS, SPEND, sales_column(attribution_days), orders_column(attribution_days),
            units_column(attribution_days), CTR, CPC, conversion_rate_column(attribution_days), ACOS]


def add_ratios(frame: pd.DataFrame, attribution_days: int) -> pd.DataFrame:
    """Returns a copy with CTR %, CPC, CVR % and ACoS % recomputed from the row totals.

    Ratios are 0 when the denominator is 0; canonical columns are reordered in console order
    and hidden "_" columns are kept last.
    """
    sales = sales_column(attribution_days)
    orders = orders_column(attribution_days)
    missing = [column for column in (IMPRESSIONS, CLICKS, SPEND, sales, orders) if column not in frame.columns]
    if missing:
        raise ValueError(f"Search term frame is missing columns needed for ratios: {missing}")

    with_ratios = frame.copy()
    impressions = _numeric(with_ratios[IMPRESSIONS])
    clicks = _numeric(with_ratios[CLICKS])
    spend = _numeric(with_ratios[SPEND])
    with_ratios[CTR] = _ratio(clicks * 100, impressions)
    with_ratios[CPC] = _ratio(spend, clicks)
    with_ratios[conversion_rate_column(attribution_days)] = _ratio(_numeric(with_ratios[orders]) * 100, clicks)
    with_ratios[ACOS] = _ratio(spend * 100, _numeric(with_ratios[sales]))
    return _in_console_order(with_ratios, attribution_days)


def _numeric(column: pd.Series) -> pd.Series:
    return pd.to_numeric(column, errors="coerce").fillna(0).astype("float64")


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    positive = denominator.where(denominator > 0)
    return (numerator / positive).fillna(0).round(2)


def _in_console_order(frame: pd.DataFrame, attribution_days: int) -> pd.DataFrame:
    canonical = [column for column in console_columns(attribution_days) if column in frame.columns]
    hidden = [column for column in frame.columns if str(column).startswith("_")]
    others = [column for column in frame.columns if column not in canonical and column not in hidden]
    return frame[canonical + others + hidden]


@dataclass(frozen=True, eq=False)
class SearchTermSource:
    frame: pd.DataFrame
    source: str
    currency_code: str
    label: str
    signature: str
    attribution_days: int
    bulk_ready: bool
    profile_id: str = ""
    window_start: date | None = None
    window_end: date | None = None

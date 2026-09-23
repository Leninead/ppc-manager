"""Sponsored Brands / Sponsored Display campaigns and idle targets, read next to the SP campaigns.

Kept apart from `campaign_provider` on purpose: the SP frame feeds the saved AI analysis and the MCP,
whose inputs must not change when SB and SD show up in M6. Both reads answer None while the database
lacks migration 015 (the seconds between "Deploy" and "DB migrate"), so the SP page keeps working.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from core.amazon_ads.campaign_provider import (
    ACOS,
    BID_STRATEGY,
    BUDGET_AMOUNT,
    CAMPAIGN_ID,
    CAMPAIGN_NAME,
    CLICKS,
    CPC,
    CTR,
    FRAME_COLUMNS,
    IMPRESSIONS,
    PORTFOLIO_NAME,
    PURCHASES,
    ROAS,
    SALES,
    START_DATE,
    STATE,
    TOTAL_COST,
    TYPE,
)
from core.amazon_ads.ad_entities import AD_GROUPS_TABLE
from core.amazon_ads.report_provider import READ_TIMEOUT_SECONDS, ReportReadError, _numbers, _portfolio_label
from core.integrations.store import _error_message, _Rest

log = logging.getLogger(__name__)

PRODUCT_CAMPAIGNS_RPC = "product_campaigns_between"
GRADUATION_TARGETS_RPC = "graduation_targets_between"
PRODUCT_TYPES = {"SP": "Sponsored Products", "SB": "Sponsored Brands", "SD": "Sponsored Display"}
PRODUCT_CODES = {name: code for code, name in PRODUCT_TYPES.items()}
# SB and SD count a purchase after a click or a view; SP only after a click. The click-only numbers go
# along so the AM can compare products on the same basis.
PURCHASES_CLICKS = "Purchases (clicks)"
SALES_CLICKS = "Sales (clicks)"
PRODUCT_FRAME_COLUMNS = FRAME_COLUMNS + (PURCHASES_CLICKS, SALES_CLICKS)

TARGET_PRODUCT = "Producto"
TARGET_TEXT = "Targeting"
TARGET_KIND = "Tipo de target"
TARGET_MATCH = "Match type"
TARGET_BID = "Bid"
TARGET_ID = "Target ID"
IDLE_TARGET_COLUMNS = (TARGET_PRODUCT, CAMPAIGN_NAME, TARGET_TEXT, TARGET_KIND, TARGET_MATCH, TARGET_BID,
                       CAMPAIGN_ID, TARGET_ID)
TARGET_KIND_LABELS = {"keyword": "Keyword", "product": "Producto", "auto": "Automático", "theme": "Tema",
                      "audience": "Audiencia"}
# Campaign Manager's names for SB's bidding and SD's ad group optimization; an unlisted code shows as it came. SB
# without automated bidding is "Fixed bids", as the Campaign CSV export writes it (Love To Dream MX, 18/09).
BID_STRATEGY_LABELS = {
    "SB": {"MANUAL": "Fixed bids", "AUTOMATED": "Automated bidding",
           "MAXIMIZE_IMMEDIATE_SALES": "Automated bidding",
           "MAXIMIZE_NEW_TO_BRAND_CUSTOMERS": "Automated bidding - new-to-brand customers"},
    "SD": {"clicks": "Optimize for page visits", "conversions": "Optimize for conversions",
           "reach": "Optimize for reach", "leads": "Optimize for leads"},
}

_CAMPAIGN_TEXT = ("ad_product", "campaign_id", "name", "state", "start_date", "budget_type", "cost_type",
                  "portfolio_id", "portfolio_name", "is_multi_ad_groups", "bid_strategy", "metrics_known",
                  "currency_code")
_CAMPAIGN_COUNTS = ("impressions", "clicks", "purchases", "purchases_clicks", "viewable_impressions")
_CAMPAIGN_AMOUNTS = ("cost", "sales", "sales_clicks")
_TARGET_TEXT = ("ad_product", "target_id", "campaign_id", "campaign_name", "ad_group_id", "target_kind",
                "target_text", "match_type")
# PostgREST's "function not found" when the database predates migration 015.
_MISSING_FUNCTION_CODE = "PGRST202"
# PostgREST v12's code for a table the database does not have yet (migration 018, before "DB migrate").
_MISSING_TABLE_CODE = "42P01"


@dataclass(frozen=True)
class ProductCampaigns:
    """SB and SD campaigns in the export's columns, plus the click-only purchases and sales."""

    frame: pd.DataFrame
    # SB campaigns Amazon's v3 reports leave out while in preview (isMultiAdGroupsEnabled = false), until the
    # v2 report has loaded their history: their metrics are unknown, not zero, and never read as ghosts.
    without_metrics: frozenset[str]


@dataclass(frozen=True)
class IdleTargets:
    """Enabled targets of enabled campaigns without a single impression in the range."""

    frame: pd.DataFrame
    # How many targets were looked at per product ("SP", "SB", "SD"), for "N of M". A product with
    # none is absent: its targeting has not synced yet, or it has no enabled target to look at.
    considered: dict[str, int]
    # Whether any SP ad group state of the profile is stored: only a known paused ad group leaves its targets out.
    sp_ad_groups_known: bool = False


class ProductProvider:
    def __init__(self, rest: _Rest):
        self._rest = rest

    def campaigns(self, profile_id: str, start: date, end: date) -> ProductCampaigns | None:
        action = "leer las campañas SB y SD"
        rows = self._read(PRODUCT_CAMPAIGNS_RPC, profile_id, start, end, action)
        if rows is None:
            return None
        try:
            return product_campaigns(_read_campaigns(rows))
        except ValueError as exc:
            raise ReportReadError(_error_message(exc, action)) from exc

    def idle_targets(self, profile_id: str, start: date, end: date) -> IdleTargets | None:
        action = "leer los targets sin impresiones"
        rows = self._read(GRADUATION_TARGETS_RPC, profile_id, start, end, action)
        if rows is None:
            return None
        try:
            targets = _read_targets(rows)
            ad_groups_known = self._knows_sp_ad_groups(profile_id)
        except (requests.RequestException, ValueError) as exc:
            raise ReportReadError(_error_message(exc, action)) from exc
        return idle_targets(targets, sp_ad_groups_known=ad_groups_known)

    def _knows_sp_ad_groups(self, profile_id: str) -> bool:
        """Whether graduation knows the state of any SP ad group of the profile, the data its exclusion reads."""
        try:
            rows = self._rest.select(AD_GROUPS_TABLE, {"select": "ad_group_id", "profile_id": f"eq.{profile_id}",
                                                       "ad_product": "eq.SP", "limit": "1"})
        except requests.HTTPError as exc:
            if _is_missing_table(exc):
                return False
            raise
        return bool(rows)

    def _read(self, rpc: str, profile_id: str, start: date, end: date, action: str) -> bytes | None:
        if end < start:
            raise ValueError(f"range ends before it starts: {start}..{end}")
        try:
            return self._rest.rpc_csv(
                rpc, {"p_profile_id": profile_id, "p_from": start.isoformat(), "p_to": end.isoformat()},
                timeout_s=READ_TIMEOUT_SECONDS)
        except requests.HTTPError as exc:
            if _is_missing_function(exc):
                log.info("amazon ads: %s does not exist yet (migration 015 pending)", rpc)
                return None
            raise ReportReadError(_error_message(exc, action)) from exc
        except requests.RequestException as exc:
            raise ReportReadError(_error_message(exc, action)) from exc


def product_campaigns(totals: pd.DataFrame) -> ProductCampaigns:
    """The export's columns for SB and SD; ratios as fractions, like the SP frame."""
    live = totals[totals["state"].str.strip().str.upper() != "ARCHIVED"]
    live = live.sort_values(["ad_product", "name", "campaign_id"], kind="mergesort").reset_index(drop=True)
    # PostgREST's CSV writes a boolean the way Postgres prints it: "t" / "f", not true / false.
    without = live["metrics_known"].str.strip().str.lower().isin(("f", "false"))
    cost, sales, clicks, impressions = live["cost"], live["sales"], live["clicks"], live["impressions"]
    frame = pd.DataFrame({
        CAMPAIGN_NAME: live["name"],
        CAMPAIGN_ID: live["campaign_id"],
        STATE: live["state"].str.strip().str.upper(),
        TYPE: live["ad_product"].map(PRODUCT_TYPES),
        PORTFOLIO_NAME: [_portfolio_label(portfolio_id, name) for portfolio_id, name
                         in zip(live["portfolio_id"], live["portfolio_name"])],
        START_DATE: live["start_date"],
        BID_STRATEGY: [bid_strategy_label(product, code) for product, code
                       in zip(live["ad_product"], live["bid_strategy"])],
        BUDGET_AMOUNT: live["budget_amount"],
        # Nullable integers: an SB campaign the reports leave out has no count at all, not a zero.
        IMPRESSIONS: impressions.astype("Int64"),
        CLICKS: clicks.astype("Int64"),
        CTR: clicks / impressions.where(impressions > 0),
        TOTAL_COST: cost,
        CPC: cost / clicks.where(clicks > 0),
        PURCHASES: live["purchases"].astype("Int64"),
        SALES: sales,
        ACOS: cost / sales.where(sales > 0),
        ROAS: sales / cost.where(cost > 0),
        PURCHASES_CLICKS: live["purchases_clicks"].astype("Int64"),
        SALES_CLICKS: live["sales_clicks"],
    }, columns=list(PRODUCT_FRAME_COLUMNS))
    unknown = without.to_numpy()
    frame.loc[unknown, [IMPRESSIONS, CLICKS, PURCHASES, PURCHASES_CLICKS]] = pd.NA
    frame.loc[unknown, [CTR, TOTAL_COST, CPC, SALES, ACOS, ROAS, SALES_CLICKS]] = float("nan")
    return ProductCampaigns(frame=frame, without_metrics=frozenset(live.loc[without, "campaign_id"]))


def idle_targets(rows: pd.DataFrame, *, sp_ad_groups_known: bool = False) -> IdleTargets:
    """The targets without impressions, out of every target looked at."""
    considered = {product: int(count) for product, count in rows.groupby("ad_product").size().items()}
    idle = rows[rows["impressions"] <= 0]
    frame = pd.DataFrame({
        TARGET_PRODUCT: idle["ad_product"],
        CAMPAIGN_NAME: idle["campaign_name"],
        TARGET_TEXT: idle["target_text"],
        TARGET_KIND: idle["target_kind"].map(TARGET_KIND_LABELS).fillna(idle["target_kind"]),
        TARGET_MATCH: idle["match_type"],
        TARGET_BID: idle["bid"],
        CAMPAIGN_ID: idle["campaign_id"],
        TARGET_ID: idle["target_id"],
    }, columns=list(IDLE_TARGET_COLUMNS)).reset_index(drop=True)
    return IdleTargets(frame=frame, considered=considered, sp_ad_groups_known=sp_ad_groups_known)


def bid_strategy_label(ad_product: str, code: str) -> str:
    """"clicks,conversions" in SD -> "Optimize for page visits / Optimize for conversions"."""
    labels = BID_STRATEGY_LABELS.get(ad_product, {})
    return " / ".join(labels.get(part.strip(), part.strip()) for part in str(code or "").split(",") if part.strip())


def with_click_columns(sp_frame: pd.DataFrame) -> pd.DataFrame:
    """The SP frame with the click-only columns: SP counts only clicks, so they are its own numbers."""
    frame = sp_frame.copy()
    frame[PURCHASES_CLICKS] = frame[PURCHASES]
    frame[SALES_CLICKS] = frame[SALES]
    return frame


def all_campaigns(sp_frame: pd.DataFrame, products: ProductCampaigns | None) -> pd.DataFrame:
    """SP, SB and SD in one frame with the click-only columns, as M6 shows them under «Todos»; SP as it
    came when the account has no other product."""
    if products is None or products.frame.empty:
        return sp_frame
    return pd.concat([with_click_columns(sp_frame), products.frame], ignore_index=True)


def campaigns_to_analyze(sp_frame: pd.DataFrame, products: ProductCampaigns | None) -> pd.DataFrame:
    """`all_campaigns` without the SB campaigns whose metrics are unknown: what the analyzer diagnoses,
    in the page, the saved analysis and the chat alike."""
    frame = all_campaigns(sp_frame, products)
    if products is None or not products.without_metrics:
        return frame
    return frame[~frame[CAMPAIGN_ID].isin(products.without_metrics)].reset_index(drop=True)


def enabled_without_metrics(products: ProductCampaigns | None) -> int:
    """How many enabled SB campaigns are left out of the diagnosis because their metrics are unknown."""
    if products is None or not products.without_metrics:
        return 0
    frame = products.frame
    return int((frame[CAMPAIGN_ID].isin(products.without_metrics) & frame[STATE].eq("ENABLED")).sum())


def _read_campaigns(csv_bytes: bytes) -> pd.DataFrame:
    fields = _CAMPAIGN_TEXT + ("budget_amount",) + _CAMPAIGN_COUNTS + _CAMPAIGN_AMOUNTS
    totals = _read_csv(csv_bytes, fields, PRODUCT_CAMPAIGNS_RPC)
    for field in _CAMPAIGN_TEXT:
        totals[field] = totals[field].str.replace("\\\\", "\\", regex=False)
    for field in _CAMPAIGN_COUNTS:
        totals[field] = _numbers(totals, field, PRODUCT_CAMPAIGNS_RPC).round().astype("int64")
    for field in _CAMPAIGN_AMOUNTS:
        totals[field] = _numbers(totals, field, PRODUCT_CAMPAIGNS_RPC).astype("float64")
    totals["budget_amount"] = _optional_numbers(totals, "budget_amount", PRODUCT_CAMPAIGNS_RPC)
    return totals


def _read_targets(csv_bytes: bytes) -> pd.DataFrame:
    fields = _TARGET_TEXT + ("bid", "impressions")
    rows = _read_csv(csv_bytes, fields, GRADUATION_TARGETS_RPC)
    for field in _TARGET_TEXT:
        rows[field] = rows[field].str.replace("\\\\", "\\", regex=False)
    rows["bid"] = _optional_numbers(rows, "bid", GRADUATION_TARGETS_RPC)
    rows["impressions"] = _numbers(rows, "impressions", GRADUATION_TARGETS_RPC).round().astype("int64")
    return rows


def _read_csv(csv_bytes: bytes, fields: tuple[str, ...], rpc: str) -> pd.DataFrame:
    try:
        if csv_bytes.strip():
            # keep_default_na=False: a campaign or keyword named "NA" is text, not a missing value.
            frame = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="utf-8")
        else:
            frame = pd.DataFrame({field: pd.Series(dtype=str) for field in fields})
        missing = [field for field in fields if field not in frame.columns]
        if missing:
            raise ValueError(f"{rpc} answered without columns {missing}")
    except ValueError as exc:
        raise ReportReadError(_error_message(exc, f"leer {rpc}")) from exc
    return frame


def _optional_numbers(frame: pd.DataFrame, field: str, rpc: str) -> pd.Series:
    """Empty is unknown (NaN); anything else must be a number."""
    raw = frame[field].str.strip()
    parsed = pd.to_numeric(raw, errors="coerce")
    unreadable = parsed.isna() & raw.ne("")
    if unreadable.any():
        raise ReportReadError(_error_message(ValueError(f"{rpc} answered a non-numeric {field}"), f"leer {rpc}"))
    return parsed


def _is_missing_function(exc: requests.HTTPError) -> bool:
    return _is_not_found(exc, _MISSING_FUNCTION_CODE)


def _is_missing_table(exc: requests.HTTPError) -> bool:
    return _is_not_found(exc, _MISSING_TABLE_CODE)


def _is_not_found(exc: requests.HTTPError, code: str) -> bool:
    response = exc.response
    if response is None or response.status_code != 404:
        return False
    try:
        return str((response.json() or {}).get("code") or "") == code
    except ValueError:
        return False

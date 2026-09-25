"""Module-agnostic read API for the Sponsored Products structure: campaigns, placement adjustments, ad groups,
keywords and targets, product ads and negatives, as Amazon Ads last listed them.

Reads `sp_structure_between` over PostgREST. The structure is the daily snapshot of the entity listings; the
metrics of the campaigns and targets are summed over the range from the reports. `rows` keeps the database's
names for code and the MCP; `frame` puts the same rows under the Bulk File's headers, which the Bulk readers of
the modules already understand. `sp_structure_counts` says how many rows each family has without reading them,
which is how an account's hundreds of thousands of negatives are sized before anything asks for them. Answers
None while the database lacks migration 018.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import requests

from core.amazon_ads.product_provider import _is_missing_function, _optional_numbers, _read_csv
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

STRUCTURE_RPC = "sp_structure_between"
STRUCTURE_COUNTS_RPC = "sp_structure_counts"
SB_SD_TARGETS_RPC = "sb_sd_targets_between"
TARGET_TOP_OF_SEARCH_RPC = "target_top_of_search_between"

CAMPAIGN = "campaign"
BIDDING_ADJUSTMENT = "bidding_adjustment"
AD_GROUP = "ad_group"
KEYWORD = "keyword"
PRODUCT_TARGETING = "product_targeting"
PRODUCT_AD = "product_ad"
NEGATIVE_KEYWORD = "negative_keyword"
CAMPAIGN_NEGATIVE_KEYWORD = "campaign_negative_keyword"
NEGATIVE_PRODUCT_TARGETING = "negative_product_targeting"
CAMPAIGN_NEGATIVE_PRODUCT_TARGETING = "campaign_negative_product_targeting"
ENTITIES = (CAMPAIGN, BIDDING_ADJUSTMENT, AD_GROUP, KEYWORD, PRODUCT_TARGETING, PRODUCT_AD, NEGATIVE_KEYWORD,
            CAMPAIGN_NEGATIVE_KEYWORD, NEGATIVE_PRODUCT_TARGETING, CAMPAIGN_NEGATIVE_PRODUCT_TARGETING)
NEGATIVE_ENTITIES = (NEGATIVE_KEYWORD, CAMPAIGN_NEGATIVE_KEYWORD, NEGATIVE_PRODUCT_TARGETING,
                     CAMPAIGN_NEGATIVE_PRODUCT_TARGETING)

ROW_COLUMNS = (
    "entity", "campaign_id", "ad_group_id", "entity_id",
    "campaign_name", "ad_group_name", "portfolio_id", "portfolio_name",
    "state", "targeting_type", "budget_amount", "budget_type", "bidding_strategy",
    "placement", "percentage", "asin", "sku",
    "target_kind", "target_text", "match_type",
    "default_bid", "own_bid", "bid",
    "impressions", "clicks", "cost", "purchases_7d", "sales_7d",
    "purchases_14d", "sales_14d", "metrics_known", "currency_code", "listed_at",
)
COUNT_COLUMNS = ("entity", "entity_rows", "listed_at")
# An SB or SD keyword or target: the SP target's columns, its campaign's state, and SB's and SD's attribution.
SB_SD_TARGET_COLUMNS = (
    "entity", "campaign_id", "ad_group_id", "entity_id", "campaign_name", "campaign_state", "cost_type", "ad_group_name",
    "state", "target_kind", "target_text", "match_type", "default_bid", "own_bid", "bid",
    "impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks", "sales_clicks",
    "top_of_search_share", "metrics_known", "currency_code", "listed_at",
)
_SB_SD_TEXT_FIELDS = ("entity", "campaign_id", "ad_group_id", "entity_id", "campaign_name", "campaign_state",
                      "cost_type", "ad_group_name", "state", "target_kind", "target_text", "match_type",
                      "currency_code")
_SB_SD_COUNT_FIELDS = ("impressions", "clicks", "purchases", "purchases_clicks")
_SB_SD_AMOUNT_FIELDS = ("cost", "sales", "sales_clicks")
STRUCTURE_COLUMNS = ("Entity", "Campaign ID", "Ad Group ID", "Ad ID", "Keyword ID", "Product Targeting ID",
                     "Campaign Name", "Ad Group Name", "Portfolio Name", "State", "Targeting Type", "Daily Budget",
                     "Bidding Strategy", "Placement", "Percentage", "ASIN", "SKU", "Ad Group Default Bid", "Bid",
                     "Keyword Text", "Match Type", "Product Targeting Expression", "Impressions", "Clicks", "Spend",
                     "Sales", "Orders")

_ENTITY_LABELS = {
    CAMPAIGN: "Campaign",
    BIDDING_ADJUSTMENT: "Bidding Adjustment",
    AD_GROUP: "Ad Group",
    KEYWORD: "Keyword",
    PRODUCT_TARGETING: "Product Targeting",
    PRODUCT_AD: "Product Ad",
    NEGATIVE_KEYWORD: "Negative Keyword",
    CAMPAIGN_NEGATIVE_KEYWORD: "Campaign Negative Keyword",
    NEGATIVE_PRODUCT_TARGETING: "Negative Product Targeting",
    # Named as Amazon's bulksheet names it; no downloaded bulk in the repo has one to check against.
    CAMPAIGN_NEGATIVE_PRODUCT_TARGETING: "Campaign Negative Product Targeting",
}
_ENTITY_RANK = {entity: rank for rank, entity in enumerate(ENTITIES)}
_KEYWORD_ENTITIES = (KEYWORD, NEGATIVE_KEYWORD, CAMPAIGN_NEGATIVE_KEYWORD)
_PRODUCT_ENTITIES = (PRODUCT_TARGETING, NEGATIVE_PRODUCT_TARGETING, CAMPAIGN_NEGATIVE_PRODUCT_TARGETING)
_TARGETING_TYPES = {"AUTO": "Auto", "MANUAL": "Manual"}
# The values a bulk upload accepts (_archive/docs/AmazonBulkUploadGuide.md, "Regla #5"), not the display names.
_BULK_BID_STRATEGIES = {
    "MANUAL": "Fixed bid",
    "LEGACY_FOR_SALES": "Dynamic bids - down only",
    "AUTO_FOR_SALES": "Dynamic bids - up and down",
}
# Negative Broad is not among the values the repo's bulk validator has seen (core/bulk/parser.py:391).
_MATCH_TYPES = {
    "EXACT": "Exact",
    "PHRASE": "Phrase",
    "BROAD": "Broad",
    "NEGATIVE_EXACT": "Negative Exact",
    "NEGATIVE_PHRASE": "Negative Phrase",
    "NEGATIVE_BROAD": "Negative Broad",
}
_DAILY_BUDGET = "DAILY"
_ATTRIBUTION_FIELDS = {
    SELLER_ATTRIBUTION_DAYS: ("sales_7d", "purchases_7d"),
    VENDOR_ATTRIBUTION_DAYS: ("sales_14d", "purchases_14d"),
}

_TEXT_FIELDS = ("entity", "campaign_id", "ad_group_id", "entity_id", "campaign_name", "ad_group_name",
                "portfolio_id", "portfolio_name", "state", "targeting_type", "budget_type", "bidding_strategy",
                "placement", "asin", "sku", "target_kind", "target_text", "match_type", "currency_code")
_OPTIONAL_FIELDS = ("budget_amount", "percentage", "default_bid", "own_bid", "bid")
_COUNT_FIELDS = ("impressions", "clicks", "purchases_7d", "purchases_14d")
_AMOUNT_FIELDS = ("cost", "sales_7d", "sales_14d")
_ORDER_FIELDS = ("campaign_name", "campaign_id", "_rank", "ad_group_name", "target_text", "entity_id", "placement")
_READ_ACTION = "leer la estructura SP de Amazon Ads"
_COUNT_ACTION = "contar la estructura SP de Amazon Ads"
_SB_SD_ACTION = "leer los keywords y targets SB o SD de Amazon Ads"
_TOP_OF_SEARCH_ACTION = "leer el top of search de los targets de Amazon Ads"


@dataclass(frozen=True)
class SpStructure:
    # The RPC rows, typed and under its names: what code and the MCP read.
    rows: pd.DataFrame
    # The same rows under the Bulk File's headers and values: what the modules read.
    frame: pd.DataFrame
    currency_code: str
    label: str
    profile_id: str
    window_start: date
    window_end: date
    attribution_days: int
    # Entity family -> its latest listing time, for "estructura al ..."; negatives: when their last complete run began.
    listed_at: dict[str, datetime]


@dataclass(frozen=True)
class StructureCounts:
    # Entity family -> its rows once it has some; the negative families, at 0 too, once a complete run exists.
    rows: dict[str, int]
    # Entity family -> its latest listing time; for the negatives, when their last complete run began.
    listed_at: dict[str, datetime]


class StructureProvider:
    def __init__(self, rest: _Rest):
        self._rest = rest

    def sp_structure(self, option: ProfileOption, start: date, end: date, *,
                     entities: tuple[str, ...] | None = None,
                     campaign_ids: tuple[str, ...] = ()) -> SpStructure | None:
        """One profile's SP structure as last listed, with the metrics summed over [start, end].

        `entities` narrows it to those families and `campaign_ids` to those campaigns.
        """
        args = _window_args(option, start, end, campaign_ids)
        unknown = sorted(set(entities or ()) - set(ENTITIES))
        if unknown:
            raise ValueError(f"unknown SP structure entities: {unknown}")
        if entities is not None:
            args["p_entities"] = list(entities)
        csv_bytes = self._read(STRUCTURE_RPC, args, _READ_ACTION)
        if csv_bytes is None:
            return None
        try:
            rows = _read_rows(csv_bytes)
        except ValueError as exc:
            raise ReportReadError(_error_message(exc, _READ_ACTION)) from exc

        attribution_days = _attribution_days(option.account_type)
        log.info("amazon ads SP structure read: profile %s %s..%s, %d rows, %dd attribution",
                 option.profile_id, start, end, len(rows), attribution_days)
        return SpStructure(
            rows=rows,
            frame=bulk_frame(rows, attribution_days),
            currency_code=option.currency_code or _single_currency(rows),
            label=f"{option.label} · {option.country_code}" if option.country_code else option.label,
            profile_id=option.profile_id,
            window_start=start,
            window_end=end,
            attribution_days=attribution_days,
            listed_at=_listing_times(rows),
        )

    def sp_structure_counts(self, option: ProfileOption, start: date, end: date, *,
                            campaign_ids: tuple[str, ...] = ()) -> StructureCounts | None:
        """How many rows each family of one profile's SP structure has, and when each was listed, without the rows.

        `campaign_ids` narrows it to those campaigns.
        """
        args = _window_args(option, start, end, campaign_ids)
        csv_bytes = self._read(STRUCTURE_COUNTS_RPC, args, _COUNT_ACTION)
        if csv_bytes is None:
            return None
        try:
            counts = _read_counts(csv_bytes)
        except ValueError as exc:
            raise ReportReadError(_error_message(exc, _COUNT_ACTION)) from exc
        log.info("amazon ads SP structure counted: profile %s %s..%s, %d families, %d rows",
                 option.profile_id, start, end, len(counts.rows), sum(counts.rows.values()))
        return counts

    def sb_sd_targets(self, option: ProfileOption, start: date, end: date, product: str, *,
                      campaign_ids: tuple[str, ...] = ()) -> pd.DataFrame | None:
        """One profile's SB or SD keywords and targets as last listed, in SB_SD_TARGET_COLUMNS, with the metrics
        summed over [start, end]. None while the database lacks migration 019."""
        if product not in ("SB", "SD"):
            raise ValueError(f"sb_sd_targets reads SB or SD, not {product!r}")
        args = {**_window_args(option, start, end, campaign_ids), "p_ad_product": product}
        csv_bytes = self._read(SB_SD_TARGETS_RPC, args, _SB_SD_ACTION)
        if csv_bytes is None:
            return None
        try:
            return _read_sb_sd_targets(csv_bytes)
        except ValueError as exc:
            raise ReportReadError(_error_message(exc, _SB_SD_ACTION)) from exc

    def target_top_of_search(self, option: ProfileOption, start: date, end: date,
                             product: str) -> dict[str, float] | None:
        """Target id -> its top-of-search impression share over [start, end], for the targets Amazon gave one.
        None while the database lacks migration 019."""
        args = {**_window_args(option, start, end, ()), "p_ad_product": product}
        csv_bytes = self._read(TARGET_TOP_OF_SEARCH_RPC, args, _TOP_OF_SEARCH_ACTION)
        if csv_bytes is None:
            return None
        try:
            rows = _read_csv(csv_bytes, ("target_id", "top_of_search_share"), TARGET_TOP_OF_SEARCH_RPC)
            shares = _optional_numbers(rows, "top_of_search_share", TARGET_TOP_OF_SEARCH_RPC)
        except ValueError as exc:
            raise ReportReadError(_error_message(exc, _TOP_OF_SEARCH_ACTION)) from exc
        return {target_id: float(share) for target_id, share in zip(rows["target_id"], shares) if share == share}

    def _read(self, rpc: str, args: dict, action: str) -> bytes | None:
        """The RPC's CSV answer, or None while the database lacks it."""
        try:
            return self._rest.rpc_csv(rpc, args, timeout_s=READ_TIMEOUT_SECONDS)
        except requests.HTTPError as exc:
            if _is_missing_function(exc):
                log.info("amazon ads: %s does not exist yet (its migration is pending)", rpc)
                return None
            raise ReportReadError(_error_message(exc, action)) from exc
        except requests.RequestException as exc:
            raise ReportReadError(_error_message(exc, action)) from exc


def _window_args(option: ProfileOption, start: date, end: date, campaign_ids: tuple[str, ...]) -> dict:
    if end < start:
        raise ValueError(f"SP structure range ends before it starts: {start}..{end}")
    args = {"p_profile_id": option.profile_id, "p_from": start.isoformat(), "p_to": end.isoformat()}
    if campaign_ids:
        args["p_campaign_ids"] = list(campaign_ids)
    return args


def bulk_frame(rows: pd.DataFrame, attribution_days: int) -> pd.DataFrame:
    """The rows under the Bulk File's headers and values, in their order."""
    sales_field, orders_field = _ATTRIBUTION_FIELDS[attribution_days]
    entity = rows["entity"]
    keyword_family = entity.isin(_KEYWORD_ENTITIES)
    product_family = entity.isin(_PRODUCT_ENTITIES)
    return pd.DataFrame({
        "Entity": entity.map(_ENTITY_LABELS),
        "Campaign ID": rows["campaign_id"],
        "Ad Group ID": rows["ad_group_id"],
        "Ad ID": rows["entity_id"].where(entity.eq(PRODUCT_AD), ""),
        "Keyword ID": rows["entity_id"].where(keyword_family, ""),
        "Product Targeting ID": rows["entity_id"].where(product_family, ""),
        "Campaign Name": rows["campaign_name"],
        "Ad Group Name": rows["ad_group_name"],
        "Portfolio Name": [_portfolio_label(portfolio_id, name) if kind == CAMPAIGN else ""
                           for kind, portfolio_id, name in zip(entity, rows["portfolio_id"], rows["portfolio_name"])],
        "State": rows["state"].str.lower(),
        "Targeting Type": rows["targeting_type"].map(lambda code: _TARGETING_TYPES.get(code, code)),
        "Daily Budget": rows["budget_amount"].where(rows["budget_type"].eq(_DAILY_BUDGET)),
        "Bidding Strategy": rows["bidding_strategy"].map(lambda code: _BULK_BID_STRATEGIES.get(code, code)),
        # The API's placement codes: no downloaded bulk in the repo shows the labels Amazon writes for them.
        "Placement": rows["placement"],
        "Percentage": rows["percentage"],
        "ASIN": rows["asin"],
        "SKU": rows["sku"],
        "Ad Group Default Bid": rows["default_bid"],
        "Bid": rows["bid"],
        "Keyword Text": rows["target_text"].where(keyword_family, ""),
        "Match Type": rows["match_type"].map(lambda code: _MATCH_TYPES.get(code, code)),
        "Product Targeting Expression": rows["target_text"].where(product_family, ""),
        "Impressions": rows["impressions"],
        "Clicks": rows["clicks"],
        "Spend": rows["cost"],
        "Sales": rows[sales_field],
        "Orders": rows[orders_field],
    }, columns=list(STRUCTURE_COLUMNS))


def _read_rows(csv_bytes: bytes) -> pd.DataFrame:
    """The RPC answer typed; raises ValueError on a malformed answer."""
    rows = _read_csv(csv_bytes, ROW_COLUMNS, STRUCTURE_RPC)
    for field in _TEXT_FIELDS:
        # PostgREST writes text/csv from record_out, which doubles every backslash inside a field.
        rows[field] = rows[field].str.replace("\\\\", "\\", regex=False)
    unknown = sorted(set(rows["entity"]) - set(ENTITIES))
    if unknown:
        raise ValueError(f"{STRUCTURE_RPC} answered unknown entities {unknown}")
    for field in _OPTIONAL_FIELDS:
        rows[field] = _optional_numbers(rows, field, STRUCTURE_RPC)
    known = _metrics_known(rows)
    # A row without known metrics has unknown metrics, never zeros.
    for field in _COUNT_FIELDS:
        rows[field] = _numbers(rows, field, STRUCTURE_RPC).round().astype("float64").where(known)
    for field in _AMOUNT_FIELDS:
        rows[field] = _numbers(rows, field, STRUCTURE_RPC).astype("float64").where(known)
    rows["metrics_known"] = known
    rows["listed_at"] = pd.to_datetime(rows["listed_at"], utc=True, format="ISO8601")
    # Code-point order whatever the database's collation, so one listing always pages the same.
    ordered = rows.assign(_rank=rows["entity"].map(_ENTITY_RANK)).sort_values(list(_ORDER_FIELDS), kind="mergesort")
    return ordered[list(ROW_COLUMNS)].reset_index(drop=True)


def _read_sb_sd_targets(csv_bytes: bytes) -> pd.DataFrame:
    """The SB or SD targets typed; raises ValueError on a malformed answer."""
    rows = _read_csv(csv_bytes, SB_SD_TARGET_COLUMNS, SB_SD_TARGETS_RPC)
    for field in _SB_SD_TEXT_FIELDS:
        rows[field] = rows[field].str.replace("\\\\", "\\", regex=False)
    for field in ("default_bid", "own_bid", "bid", "top_of_search_share"):
        rows[field] = _optional_numbers(rows, field, SB_SD_TARGETS_RPC)
    known = _metrics_known(rows, SB_SD_TARGETS_RPC)
    for field in _SB_SD_COUNT_FIELDS:
        rows[field] = _numbers(rows, field, SB_SD_TARGETS_RPC).round().astype("float64").where(known)
    for field in _SB_SD_AMOUNT_FIELDS:
        rows[field] = _numbers(rows, field, SB_SD_TARGETS_RPC).astype("float64").where(known)
    rows["metrics_known"] = known
    rows["listed_at"] = pd.to_datetime(rows["listed_at"], utc=True, format="ISO8601")
    ordered = rows.sort_values(["campaign_name", "campaign_id", "ad_group_name", "target_text", "entity_id"],
                               kind="mergesort")
    return ordered[list(SB_SD_TARGET_COLUMNS)].reset_index(drop=True)


def _metrics_known(rows: pd.DataFrame, rpc: str = STRUCTURE_RPC) -> pd.Series:
    # PostgREST's CSV writes a boolean the way Postgres prints it: "t" / "f", not true / false.
    raw = rows["metrics_known"].str.strip()
    unreadable = ~raw.isin(("t", "f"))
    if unreadable.any():
        raise ValueError(f"{rpc} answered a non-boolean metrics_known: {raw[unreadable].iloc[0]!r}")
    return raw.eq("t")


def _listing_times(rows: pd.DataFrame) -> dict[str, datetime]:
    latest = rows.groupby("entity")["listed_at"].max()
    return {entity: latest[entity].to_pydatetime() for entity in ENTITIES if entity in latest.index}


def _read_counts(csv_bytes: bytes) -> StructureCounts:
    """The counts RPC answer typed, in the families' order; raises ValueError on a malformed answer."""
    counts = _read_csv(csv_bytes, COUNT_COLUMNS, STRUCTURE_COUNTS_RPC)
    unknown = sorted(set(counts["entity"]) - set(ENTITIES))
    if unknown:
        raise ValueError(f"{STRUCTURE_COUNTS_RPC} answered unknown entities {unknown}")
    by_entity = counts.assign(
        entity_rows=_numbers(counts, "entity_rows", STRUCTURE_COUNTS_RPC).astype("int64"),
        listed_at=pd.to_datetime(counts["listed_at"], utc=True, format="ISO8601"),
    ).set_index("entity")
    present = [entity for entity in ENTITIES if entity in by_entity.index]
    return StructureCounts(
        rows={entity: int(by_entity.at[entity, "entity_rows"]) for entity in present},
        listed_at={entity: by_entity.at[entity, "listed_at"].to_pydatetime() for entity in present},
    )

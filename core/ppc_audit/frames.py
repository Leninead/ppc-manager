"""What PPC Audit Pro reads: one frame per entity family and ad product, under the Bulk File's headers.

A hand-uploaded Bulk File fills them from its sheets (core/ppc_audit/bulk_file.py); the synced Amazon Ads data from
the SP structure listing, the search term reports and the SB / SD reads (`frames_from_amazon_ads`). The rules in
core/ppc_audit/checks.py never know which one they got.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.amazon_ads import campaign_provider
from core.amazon_ads.product_provider import ProductCampaigns
from core.amazon_ads.report_provider import ORIGIN_AUTO, ORIGIN_PRODUCT_TARGETING
from core.amazon_ads.structure_provider import SpStructure
from core.search_term import frame as canonical
from core.search_term.frame import SOURCE_API, SOURCE_FILE

ENTITY = "Entity"
CAMPAIGN_ID = "Campaign ID"
CAMPAIGN_NAME = "Campaign Name"
AD_GROUP_ID = "Ad Group ID"
AD_GROUP_NAME = "Ad Group Name"
KEYWORD_ID = "Keyword ID"
STATE = "State"
TARGETING_TYPE = "Targeting Type"
BIDDING_STRATEGY = "Bidding Strategy"
PLACEMENT = "Placement"
PERCENTAGE = "Percentage"
ASIN = "ASIN"
BID = "Bid"
KEYWORD_TEXT = "Keyword Text"
MATCH_TYPE = "Match Type"
EXPRESSION = "Product Targeting Expression"
SEARCH_TERM = "Customer Search Term"
IMPRESSIONS = "Impressions"
CLICKS = "Clicks"
SPEND = "Spend"
SALES = "Sales"
ORDERS = "Orders"
METRICS = (IMPRESSIONS, CLICKS, SPEND, SALES, ORDERS)

# Parts the synced data can lack, each with the reason the page and the MCP say.
SP_TARGETS = "sp_targets"
SP_TARGET_METRICS = "sp_target_metrics"
SB_SD_CAMPAIGNS = "sb_sd_campaigns"
SB_KEYWORDS = "sb_keywords"
SD_TARGETS = "sd_targets"
SB_SEARCH_TERMS = "sb_search_terms"

CAMPAIGN_COLUMNS = (CAMPAIGN_ID, CAMPAIGN_NAME, STATE, TARGETING_TYPE, BIDDING_STRATEGY, *METRICS)
TARGET_COLUMNS = (CAMPAIGN_ID, CAMPAIGN_NAME, AD_GROUP_ID, AD_GROUP_NAME, KEYWORD_ID, STATE, BID, KEYWORD_TEXT,
                  MATCH_TYPE, EXPRESSION, *METRICS)
SEARCH_TERM_COLUMNS = (SEARCH_TERM, CAMPAIGN_ID, CAMPAIGN_NAME, AD_GROUP_ID, KEYWORD_TEXT, MATCH_TYPE, EXPRESSION,
                       *METRICS)

_MATCH_TITLES = {"EXACT": "Exact", "PHRASE": "Phrase", "BROAD": "Broad"}
_SPONSORED_BRANDS = "Sponsored Brands"
_SPONSORED_DISPLAY = "Sponsored Display"


@dataclass(frozen=True, eq=False)
class AuditFrames:
    sp_campaigns: pd.DataFrame
    sp_ad_groups: pd.DataFrame
    sp_keywords: pd.DataFrame
    sp_product_targets: pd.DataFrame
    sp_product_ads: pd.DataFrame
    sp_placements: pd.DataFrame
    sp_search_terms: pd.DataFrame
    sb_campaigns: pd.DataFrame
    sb_keywords: pd.DataFrame
    sb_search_terms: pd.DataFrame
    sd_campaigns: pd.DataFrame
    sd_targets: pd.DataFrame
    source: str
    # Empty for a file: its currency is not known, and the page keeps the dollar sign it always showed.
    currency_code: str = ""
    # Part -> why the synced data lacks it. A Bulk File never fills it: a missing sheet is an empty frame.
    unavailable: dict[str, str] = field(default_factory=dict)

    @property
    def from_file(self) -> bool:
        return self.source == SOURCE_FILE


def empty_frame(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})


def frames_from_amazon_ads(structure: SpStructure, search_terms: pd.DataFrame, *, attribution_days: int,
                           products: ProductCampaigns | None, sb_targets: pd.DataFrame | None,
                           sd_targets: pd.DataFrame | None, sb_search_terms: pd.DataFrame | None,
                           unavailable: dict[str, str] | None = None) -> AuditFrames:
    """The synced reads under the Bulk File's headers; a read that is None becomes an empty frame."""
    sp = structure.frame

    def entity(label: str) -> pd.DataFrame:
        return sp[sp[ENTITY] == label].reset_index(drop=True)

    campaigns = products.frame if products is not None else None
    return AuditFrames(
        sp_campaigns=entity("Campaign"),
        sp_ad_groups=entity("Ad Group"),
        sp_keywords=entity("Keyword"),
        sp_product_targets=entity("Product Targeting"),
        sp_product_ads=entity("Product Ad"),
        sp_placements=entity("Bidding Adjustment"),
        sp_search_terms=search_term_sheet(search_terms, attribution_days),
        sb_campaigns=product_campaign_sheet(campaigns, _SPONSORED_BRANDS),
        sb_keywords=sb_keyword_sheet(sb_targets),
        sb_search_terms=sb_search_term_sheet(sb_search_terms),
        sd_campaigns=product_campaign_sheet(campaigns, _SPONSORED_DISPLAY),
        sd_targets=sd_target_sheet(sd_targets),
        source=SOURCE_API,
        currency_code=structure.currency_code,
        unavailable=dict(unavailable or {}),
    )


def search_term_sheet(search_terms: pd.DataFrame, attribution_days: int) -> pd.DataFrame:
    """The canonical Search Term frame as the Bulk File's "SP Search Term Report" sheet names it."""
    if search_terms.empty:
        return empty_frame(SEARCH_TERM_COLUMNS)
    from_targeting = search_terms["_origin_match_type"].isin((ORIGIN_AUTO, ORIGIN_PRODUCT_TARGETING))
    return pd.DataFrame({
        SEARCH_TERM: search_terms[canonical.SEARCH_TERM],
        CAMPAIGN_ID: search_terms["_campaign_id"],
        CAMPAIGN_NAME: search_terms[canonical.CAMPAIGN_NAME],
        AD_GROUP_ID: search_terms["_ad_group_id"],
        KEYWORD_TEXT: search_terms["_keyword_text"].where(~from_targeting, ""),
        MATCH_TYPE: search_terms[canonical.MATCH_TYPE].map(_match_title),
        EXPRESSION: search_terms[canonical.TARGETING].where(from_targeting, ""),
        IMPRESSIONS: search_terms[canonical.IMPRESSIONS],
        CLICKS: search_terms[canonical.CLICKS],
        SPEND: search_terms[canonical.SPEND],
        SALES: search_terms[canonical.sales_column(attribution_days)],
        ORDERS: search_terms[canonical.orders_column(attribution_days)],
    }, columns=list(SEARCH_TERM_COLUMNS)).reset_index(drop=True)


def product_campaign_sheet(campaigns: pd.DataFrame | None, product_type: str) -> pd.DataFrame:
    """One ad product's campaigns from the SB / SD campaign read; a metric Amazon did not report stays NaN."""
    if campaigns is None:
        return empty_frame(CAMPAIGN_COLUMNS)
    rows = campaigns[campaigns[campaign_provider.TYPE] == product_type]
    return pd.DataFrame({
        CAMPAIGN_ID: rows[campaign_provider.CAMPAIGN_ID],
        CAMPAIGN_NAME: rows[campaign_provider.CAMPAIGN_NAME],
        STATE: rows[campaign_provider.STATE].str.lower(),
        TARGETING_TYPE: "",
        BIDDING_STRATEGY: rows[campaign_provider.BID_STRATEGY],
        IMPRESSIONS: rows[campaign_provider.IMPRESSIONS].astype("float64"),
        CLICKS: rows[campaign_provider.CLICKS].astype("float64"),
        SPEND: rows[campaign_provider.TOTAL_COST].astype("float64"),
        SALES: rows[campaign_provider.SALES].astype("float64"),
        ORDERS: rows[campaign_provider.PURCHASES].astype("float64"),
    }, columns=list(CAMPAIGN_COLUMNS)).reset_index(drop=True)


def sb_keyword_sheet(targets: pd.DataFrame | None) -> pd.DataFrame:
    """SB's keywords from its keyword and target read, with the sales Campaign Manager shows."""
    if targets is None:
        return empty_frame(TARGET_COLUMNS)
    return _target_sheet(targets[targets["target_kind"] == "keyword"])


def sd_target_sheet(targets: pd.DataFrame | None) -> pd.DataFrame:
    """SD's targets (products, audiences, Amazon's own picks), one grain: the target."""
    if targets is None:
        return empty_frame(TARGET_COLUMNS)
    return _target_sheet(targets)


def sb_search_term_sheet(search_terms: pd.DataFrame | None) -> pd.DataFrame:
    """SB's search terms as the Bulk File's "SB Search Term Report" sheet names them."""
    if search_terms is None or search_terms.empty:
        return empty_frame(SEARCH_TERM_COLUMNS)
    return pd.DataFrame({
        SEARCH_TERM: search_terms["search_term"],
        CAMPAIGN_ID: search_terms["campaign_id"],
        CAMPAIGN_NAME: search_terms["campaign_name"],
        AD_GROUP_ID: search_terms["ad_group_id"],
        KEYWORD_TEXT: search_terms["keyword_text"],
        MATCH_TYPE: search_terms["match_type"].map(_match_title),
        EXPRESSION: "",
        IMPRESSIONS: search_terms["impressions"].astype("float64"),
        CLICKS: search_terms["clicks"].astype("float64"),
        SPEND: search_terms["cost"].astype("float64"),
        SALES: search_terms["sales"].astype("float64"),
        ORDERS: search_terms["purchases"].astype("float64"),
    }, columns=list(SEARCH_TERM_COLUMNS)).reset_index(drop=True)


def _target_sheet(targets: pd.DataFrame) -> pd.DataFrame:
    keyword = targets["target_kind"].eq("keyword")
    return pd.DataFrame({
        CAMPAIGN_ID: targets["campaign_id"],
        CAMPAIGN_NAME: targets["campaign_name"],
        AD_GROUP_ID: targets["ad_group_id"],
        AD_GROUP_NAME: targets["ad_group_name"],
        KEYWORD_ID: targets["entity_id"],
        STATE: targets["state"].str.lower(),
        BID: targets["bid"],
        KEYWORD_TEXT: targets["target_text"].where(keyword, ""),
        MATCH_TYPE: targets["match_type"].map(_match_title),
        EXPRESSION: targets["target_text"].where(~keyword, ""),
        IMPRESSIONS: targets["impressions"],
        CLICKS: targets["clicks"],
        SPEND: targets["cost"],
        SALES: targets["sales"],
        ORDERS: targets["purchases"],
    }, columns=list(TARGET_COLUMNS)).reset_index(drop=True)


def _match_title(code) -> str:
    text = "" if code is None else str(code).strip()
    return _MATCH_TITLES.get(text.upper(), text)

"""The Sponsored Products campaigns that run for each ASIN and what they target: the health score's funnel part.

From the account's SP listing (core/amazon_ads/structure_provider.py): an ad group runs when its campaign is enabled,
it is not listed as paused and it has an enabled product ad. It covers an ASIN when one of those ads advertises it or
its campaign's name carries it: the name is also how a search term takes the ASIN of a product family. Its kinds are
Auto in an auto campaign; otherwise the match types of its enabled keywords, and PAT with enabled product targets.
From a Campaign CSV, which only has campaign names, the ASIN and the kinds are words of the name, as the module always
read it. The page, the analysis worker and the MCP server read the listing through here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import ClassVar

import pandas as pd

from core.amazon_ads.report_provider import ProfileOption
from core.amazon_ads.structure_listing import FamilyListing, family_listing
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    CAMPAIGN,
    KEYWORD,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    SpStructure,
    StructureProvider,
)
from core.ppc_insights.asin_health import WHOLE_ACCOUNT, find_column

AUTO = "Auto"
BROAD = "Broad"
PHRASE = "Phrase"
EXACT = "Exact"
PAT = "PAT"
MANUAL = "Manual"
LISTING_ORIGIN = "listing"
FILE_ORIGIN = "file"
LISTING_ENTITIES = (CAMPAIGN, AD_GROUP, KEYWORD, PRODUCT_TARGETING, PRODUCT_AD)
STRUCTURE_PENDING_REASON = "La base todavía no tiene la estructura de Sponsored Products (falta una migración)."
NOT_LISTED_REASON = "Todavía no se listaron {what} de Sponsored Products de esta cuenta: se listan una vez por día."
REFUSED_REASON = "Amazon rechazó el listado de {what} de Sponsored Products de esta cuenta: «{refusal}»."

_ENABLED = "ENABLED"
_AUTO_TARGETING = "AUTO"
_MATCH_KINDS = {"BROAD": BROAD, "PHRASE": PHRASE, "EXACT": EXACT}
_AD_GROUP_COLUMNS = ["campaign_id", "campaign_name", "asins", "kinds"]
# What the coverage needs listed, and how the page names each one when it is not. Keywords and product targets come
# from one listing: an account with only one of them has the other listed too.
_REQUIRED_FAMILIES = (((CAMPAIGN,), "las campañas"), ((PRODUCT_AD,), "los anuncios"),
                      ((KEYWORD, PRODUCT_TARGETING), "los keywords y product targets"))


@dataclass(frozen=True)
class AsinCampaigns:
    """The campaigns that run for one ASIN and the kinds of targeting among them."""

    campaigns: int
    kinds: frozenset = frozenset()

    @property
    def funnel_complete(self) -> bool:
        return AUTO in self.kinds and EXACT in self.kinds

    @property
    def kinds_label(self) -> str:
        return ", ".join(sorted(self.kinds)) if self.kinds else "—"


@dataclass(frozen=True, eq=False)
class ListedCampaigns:
    """The account's running SP ad groups as last listed: each one's campaign, the ASINs it advertises and its kinds."""

    origin: ClassVar[str] = LISTING_ORIGIN
    ad_groups: pd.DataFrame
    listed_at: datetime | None = None

    @classmethod
    def from_rows(cls, rows: pd.DataFrame, listed_at: datetime | None = None) -> ListedCampaigns:
        """From SpStructure.rows of LISTING_ENTITIES."""
        entity, state = rows["entity"], rows["state"].fillna("").str.upper()
        campaigns = rows[entity.eq(CAMPAIGN) & state.eq(_ENABLED)].drop_duplicates("campaign_id")
        names = dict(zip(campaigns["campaign_id"], campaigns["campaign_name"]))
        auto_campaigns = set(campaigns.loc[campaigns["targeting_type"].str.upper().eq(_AUTO_TARGETING), "campaign_id"])
        # An ad group never listed counts as enabled, as in Target Graduation.
        paused_ad_groups = set(rows.loc[entity.eq(AD_GROUP) & state.ne(_ENABLED), "ad_group_id"])
        live = rows[state.eq(_ENABLED) & rows["campaign_id"].isin(names.keys())
                    & ~rows["ad_group_id"].isin(paused_ad_groups)]

        ads = live[live["entity"].eq(PRODUCT_AD)]
        running = ads.groupby("ad_group_id", sort=True).agg(
            campaign_id=("campaign_id", "first"),
            asins=("asin", lambda asins: frozenset(asins.fillna("").str.strip().str.upper()) - {""}))
        keywords = live[live["entity"].eq(KEYWORD)]
        keyword_kinds = (keywords.assign(kind=keywords["match_type"].str.upper().map(_MATCH_KINDS))
                         .dropna(subset=["kind"]).groupby("ad_group_id")["kind"].agg(frozenset))
        product_targets = live[live["entity"].eq(PRODUCT_TARGETING)]
        targeted = set(product_targets.loc[~product_targets["campaign_id"].isin(auto_campaigns), "ad_group_id"])

        kinds = [frozenset({AUTO}) if campaign_id in auto_campaigns
                 else keyword_kinds.get(ad_group_id, frozenset()) | ({PAT} if ad_group_id in targeted else set())
                 for ad_group_id, campaign_id in zip(running.index, running["campaign_id"])]
        ad_groups = pd.DataFrame({"campaign_id": running["campaign_id"].to_list(),
                                  "campaign_name": [names[campaign_id] for campaign_id in running["campaign_id"]],
                                  "asins": running["asins"].to_list(), "kinds": kinds}, columns=_AD_GROUP_COLUMNS)
        return cls(ad_groups, listed_at)

    @property
    def campaign_count(self) -> int:
        return int(self.ad_groups["campaign_id"].nunique())

    def for_asin(self, asin) -> AsinCampaigns:
        covering = self.ad_groups
        if asin != WHOLE_ACCOUNT:
            code = str(asin).strip().upper()
            advertised = covering["asins"].map(lambda asins: code in asins).astype(bool)
            named = covering["campaign_name"].fillna("").str.upper().str.contains(code, regex=False)
            covering = covering[advertised | named]
        kinds = frozenset().union(*covering["kinds"]) if len(covering) else frozenset()
        return AsinCampaigns(int(covering["campaign_id"].nunique()), kinds)


@dataclass(frozen=True, eq=False)
class FileCampaigns:
    """A Campaign CSV uploaded by hand: names and states only, so the ASIN and the kinds are words of the name."""

    origin: ClassVar[str] = FILE_ORIGIN
    frame: pd.DataFrame

    def for_asin(self, asin) -> AsinCampaigns | None:
        """None when the file has no campaign name column: nothing can be said of any ASIN."""
        col_cname = find_column(self.frame, "Campaign Name") or find_column(self.frame, "Campaign")
        if not col_cname:
            return None
        col_state = find_column(self.frame, "State") or find_column(self.frame, "Status")
        col_target = find_column(self.frame, "Targeting Type") or find_column(self.frame, "Campaign Type")
        cdf = self.frame.copy()
        if col_state:
            cdf = cdf[cdf[col_state].astype(str).str.lower() == "enabled"]
        if asin != WHOLE_ACCOUNT:
            cdf = cdf[cdf[col_cname].astype(str).str.lower().str.contains(str(asin).lower(), na=False, regex=False)]

        kinds = set()
        for cname in cdf[col_cname].astype(str):
            nl = cname.lower()
            if "auto" in nl or "discovery" in nl:
                kinds.add(AUTO)
            if "broad" in nl:
                kinds.add(BROAD)
            if "phrase" in nl:
                kinds.add(PHRASE)
            if "exact" in nl:
                kinds.add(EXACT)
            if "pat" in nl or "asin" in nl or "conq" in nl or "competitor" in nl:
                kinds.add(PAT)
        if col_target:
            for ttype in cdf[col_target].astype(str):
                tl = ttype.lower()
                if "auto" in tl:
                    kinds.add(AUTO)
                if "manual" in tl:
                    kinds.add(MANUAL)
        return AsinCampaigns(len(cdf), frozenset(kinds))


@dataclass(frozen=True, eq=False)
class CampaignListing:
    """An account's SP campaigns as last listed, or why they are unknown."""

    campaigns: ListedCampaigns | None = None
    missing_reason: str = ""
    refused: bool = False


def read_campaign_listing(rest, option: ProfileOption, day: date) -> CampaignListing:
    """Unknown until its campaigns, product ads and targets were listed. Raises ReportReadError when the base cannot
    be read."""
    # Each family is its latest listing whatever the window: one day only keeps cheap the metrics the RPC also sums.
    structure = StructureProvider(rest).sp_structure(option, day, day, entities=LISTING_ENTITIES)
    if structure is None:
        return CampaignListing(missing_reason=STRUCTURE_PENDING_REASON)
    listings = {families[0]: _listing_of(rest, structure, families) for families, _ in _REQUIRED_FAMILIES}
    for families, what in _REQUIRED_FAMILIES:
        listing = listings[families[0]]
        if listing.refusal:
            return CampaignListing(missing_reason=REFUSED_REASON.format(what=what, refusal=listing.refusal),
                                   refused=True)
        if listing.listed_at is None:
            return CampaignListing(missing_reason=NOT_LISTED_REASON.format(what=what))
    return CampaignListing(ListedCampaigns.from_rows(structure.rows, listed_at=listings[CAMPAIGN].listed_at))


def _listing_of(rest, structure: SpStructure, families: tuple[str, ...]) -> FamilyListing:
    listed = [structure.listed_at[family] for family in families if family in structure.listed_at]
    return FamilyListing(max(listed)) if listed else family_listing(rest, structure, families[0])

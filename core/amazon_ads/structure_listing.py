"""Whether an account's Sponsored Products listing can be read yet: when each family was last listed, or why not.

A family with rows was listed. One without rows was listed only if its listing job completed, and a listing Amazon
refused completes too, with no rows and the refusal as its warning.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import requests

from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.structure_provider import AD_GROUP, CAMPAIGN, KEYWORD, PRODUCT_AD, SpStructure, StructureProvider
from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    SP_AD_GROUPS_KIND,
    SP_PRODUCT_ADS_KIND,
    SP_TARGETS_KIND,
)
from core.integrations.store import _error_message, _Rest
from core.integrations.sync_jobs import SyncJobStore

LISTING_JOB_KINDS = {
    CAMPAIGN: CAMPAIGN_ENTITIES_KIND,
    AD_GROUP: SP_AD_GROUPS_KIND,
    KEYWORD: SP_TARGETS_KIND,
    PRODUCT_AD: SP_PRODUCT_ADS_KIND,
}

_LISTING_ACTION = "leer el listado de Sponsored Products de la cuenta"


@dataclass(frozen=True)
class FamilyListing:
    listed_at: datetime | None = None  # None while the family was never listed
    refusal: str = ""  # the warning of a listing Amazon refused


@dataclass(frozen=True)
class KeywordListing:
    """An account's SP campaigns, ad groups and keywords as last listed, or why they are unknown."""

    rows: pd.DataFrame | None = None  # SpStructure.rows of those three families; None while unknown
    listed_at: datetime | None = None  # when its keywords were listed
    ad_groups_listed: bool = False  # whether the ad groups' states can be read from `rows`
    refusal: str = ""

    @property
    def known(self) -> bool:
        return self.rows is not None


def family_listing(rest: _Rest, structure: SpStructure, family: str) -> FamilyListing:
    """When a family was last listed (its newest row, or a listing that completed without rows), or its refusal."""
    if family in structure.listed_at:
        return FamilyListing(structure.listed_at[family])
    try:
        job = SyncJobStore(rest).latest_completed_for_profile(structure.profile_id, LISTING_JOB_KINDS[family])
    except (requests.RequestException, ValueError) as exc:
        raise ReportReadError(_error_message(exc, _LISTING_ACTION)) from exc
    if job is None:
        return FamilyListing()
    return FamilyListing(refusal=job.warning) if job.warning else FamilyListing(job.finished_at)


def read_keyword_listing(rest: _Rest, option: ProfileOption, day: date) -> KeywordListing:
    """The account's latest SP listing of campaigns, ad groups and keywords.

    Unknown while its campaigns or keywords were never listed, and while the database lacks migration 018.
    """
    structure = StructureProvider(rest).sp_structure(option, day, day, entities=(CAMPAIGN, AD_GROUP, KEYWORD))
    if structure is None:
        return KeywordListing()
    campaigns = family_listing(rest, structure, CAMPAIGN)
    keywords = family_listing(rest, structure, KEYWORD)
    if campaigns.listed_at is None or keywords.listed_at is None:
        return KeywordListing(refusal=campaigns.refusal or keywords.refusal)
    ad_groups = family_listing(rest, structure, AD_GROUP)
    return KeywordListing(structure.rows, keywords.listed_at, ad_groups.listed_at is not None)

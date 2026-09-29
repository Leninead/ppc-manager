"""The synced Amazon Ads data PPC Audit Pro reads for one account and window, and what each part lacks.

The SP structure is the daily listing (with and without traffic); campaigns, keywords and targets carry the window's
metrics from the reports. SB and SD come from their own reads. The page and the MCP read through here, so both say
the same about a part that is missing.
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import requests

from core.amazon_ads.campaign_provider import TYPE
from core.amazon_ads.product_provider import PRODUCT_TYPES, ProductProvider
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    BIDDING_ADJUSTMENT,
    CAMPAIGN,
    KEYWORD,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    SpStructure,
    StructureProvider,
)
from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    CAMPAIGNS_KIND,
    SB_SEARCH_TERMS_KIND,
    SP_TARGETING_KIND,
    SP_TARGETS_KIND,
)
from core.integrations.store import _error_message
from core.integrations.sync_jobs import SyncJobStore
from core.ppc_audit.frames import (
    SB_KEYWORDS,
    SB_SD_CAMPAIGNS,
    SB_SEARCH_TERMS,
    SD_TARGETS,
    SP_TARGET_METRICS,
    SP_TARGETS,
    SPEND,
    AuditFrames,
    frames_from_amazon_ads,
)

log = logging.getLogger(__name__)

AUDIT_ENTITIES = (CAMPAIGN, BIDDING_ADJUSTMENT, AD_GROUP, KEYWORD, PRODUCT_TARGETING, PRODUCT_AD)
STRUCTURE_PENDING_REASON = "La base todavía no tiene la estructura de Sponsored Products (falta una migración)."
NOT_LISTED_REASON = ("Todavía no hay un listado de las campañas de Sponsored Products de esta cuenta: se listan una "
                     "vez por día.")
REFUSED_REASON = "Amazon rechazó el listado de campañas de Sponsored Products de esta cuenta: «{refusal}»."
TARGETS_NOT_LISTED = "Los keywords y product targets de Sponsored Products de esta cuenta todavía no se listaron."
TARGETS_REFUSED = "Amazon rechazó el listado de keywords y product targets de esta cuenta: «{refusal}»."
SB_SD_CAMPAIGNS_PENDING = "La base todavía no tiene las campañas de Sponsored Brands y Display (falta una migración)."
SB_SD_TARGETS_PENDING = ("La base todavía no tiene los keywords y targets de Sponsored Brands y Display (falta una "
                         "migración).")
SB_SEARCH_TERMS_PENDING = "La base todavía no tiene los search terms de Sponsored Brands (falta una migración)."
SB_SEARCH_TERMS_NOT_SYNCED = "Los search terms de Sponsored Brands de esta cuenta todavía no se sincronizaron."
METRICS_NOT_SYNCED = "Las métricas de {what} del período todavía no se sincronizaron."
_JOBS_ACTION = "leer el estado de la sincronización de Amazon Ads"


@dataclass(frozen=True, eq=False)
class SyncedAudit:
    # None while the account's SP structure cannot be audited: never listed, refused or not in the base yet.
    frames: AuditFrames | None
    missing_reason: str = ""
    refused: bool = False
    listed_at: datetime | None = None
    # The last day with metrics of each report, from its last completed request; None before the first one.
    campaigns_through: date | None = None
    targeting_through: date | None = None
    sb_search_terms_through: date | None = None


def read_synced_audit(rest, option: ProfileOption, start: date, end: date, search_terms: pd.DataFrame, *,
                      attribution_days: int) -> SyncedAudit:
    """Raises ReportReadError when the base cannot be read."""
    structures = StructureProvider(rest)
    structure = structures.sp_structure(option, start, end, entities=AUDIT_ENTITIES)
    if structure is None:
        return SyncedAudit(frames=None, missing_reason=STRUCTURE_PENDING_REASON)
    jobs = SyncJobStore(rest)
    listed_at, refusal = _listing(jobs, structure, (CAMPAIGN,), CAMPAIGN_ENTITIES_KIND)
    if listed_at is None:
        reason = REFUSED_REASON.format(refusal=refusal) if refusal else NOT_LISTED_REASON
        return SyncedAudit(frames=None, missing_reason=reason, refused=bool(refusal))

    unavailable: dict[str, str] = {}
    targets_listed, targets_refusal = _listing(jobs, structure, (KEYWORD, PRODUCT_TARGETING), SP_TARGETS_KIND)
    if targets_listed is None:
        unavailable[SP_TARGETS] = (TARGETS_REFUSED.format(refusal=targets_refusal) if targets_refusal
                                   else TARGETS_NOT_LISTED)

    products = ProductProvider(rest)
    campaigns = products.campaigns(option.profile_id, start, end, include_archived=True)
    if campaigns is None:
        unavailable[SB_SD_CAMPAIGNS] = SB_SD_CAMPAIGNS_PENDING
    sb_targets = structures.sb_sd_targets(option, start, end, "SB")
    sd_targets = structures.sb_sd_targets(option, start, end, "SD")
    if sb_targets is None:
        unavailable[SB_KEYWORDS] = SB_SD_TARGETS_PENDING
    if sd_targets is None:
        unavailable[SD_TARGETS] = SB_SD_TARGETS_PENDING

    has_sb = campaigns is not None and bool(campaigns.frame[TYPE].eq(PRODUCT_TYPES["SB"]).any())
    sb_search_terms, sb_through = None, None
    if has_sb:
        sb_search_terms = products.sb_search_terms(option.profile_id, start, end)
        sb_through = _synced_through(jobs, option.profile_id, SB_SEARCH_TERMS_KIND)
        if sb_search_terms is None:
            unavailable[SB_SEARCH_TERMS] = SB_SEARCH_TERMS_PENDING
        elif sb_through is None:
            unavailable[SB_SEARCH_TERMS] = SB_SEARCH_TERMS_NOT_SYNCED

    frames = frames_from_amazon_ads(structure, search_terms, attribution_days=attribution_days, products=campaigns,
                                    sb_targets=sb_targets, sd_targets=sd_targets, sb_search_terms=sb_search_terms,
                                    unavailable=unavailable)
    frames = dataclasses.replace(frames, unavailable={**unavailable, **_unknown_metrics(frames)})
    log.info("ppc audit: profile %s %s..%s read, %d SP campaigns, %d keywords, missing %s", option.profile_id,
             start, end, len(frames.sp_campaigns), len(frames.sp_keywords), sorted(frames.unavailable) or "nothing")
    return SyncedAudit(
        frames=frames, listed_at=listed_at,
        campaigns_through=_synced_through(jobs, option.profile_id, CAMPAIGNS_KIND),
        targeting_through=_synced_through(jobs, option.profile_id, SP_TARGETING_KIND),
        sb_search_terms_through=sb_through,
    )


def _unknown_metrics(frames: AuditFrames) -> dict[str, str]:
    """The target families listed with rows but no metrics at all in the window: their reports never synced."""
    families = ((SP_TARGET_METRICS, pd.concat([frames.sp_keywords, frames.sp_product_targets]),
                 "keywords y targets de Sponsored Products"),
                (SB_KEYWORDS, frames.sb_keywords, "keywords de Sponsored Brands"),
                (SD_TARGETS, frames.sd_targets, "targets de Sponsored Display"))
    return {part: METRICS_NOT_SYNCED.format(what=what) for part, targets, what in families
            if part not in frames.unavailable and not targets.empty and targets[SPEND].isna().all()}


def _listing(jobs: SyncJobStore, structure: SpStructure, families: tuple[str, ...],
             job_kind: str) -> tuple[datetime | None, str]:
    """When the families were last listed (their newest row, or a listing that completed without rows), or the
    refusal Amazon gave."""
    listed = [structure.listed_at[family] for family in families if family in structure.listed_at]
    if listed:
        return max(listed), ""
    job = _latest_completed(jobs, structure.profile_id, job_kind)
    if job is None:
        return None, ""
    # A listing Amazon refused also completes, with no rows and the refusal as its warning.
    return (None, job.warning) if job.warning else (job.finished_at, "")


def _synced_through(jobs: SyncJobStore, profile_id: str, job_kind: str) -> date | None:
    job = _latest_completed(jobs, profile_id, job_kind)
    return job.window_end if job is not None else None


def _latest_completed(jobs: SyncJobStore, profile_id: str, job_kind: str):
    try:
        return jobs.latest_completed_for_profile(profile_id, job_kind)
    except (requests.RequestException, ValueError) as exc:
        raise ReportReadError(_error_message(exc, _JOBS_ACTION)) from exc

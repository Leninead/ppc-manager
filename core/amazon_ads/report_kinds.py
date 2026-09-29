"""What differs between the Reporting v3 reports the worker ingests.

Requesting, polling, downloading and archiving are identical for every report, so they stay in
`ingestion_job`. Only the pieces below change, and they travel together: the columns asked for,
the mapper that reads exactly those columns, and the function that writes the day.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

from core.amazon_ads import campaign_rows, product_rows, search_term_rows
from core.amazon_ads.campaign_rows import CAMPAIGN_REPORT_SPEC
from core.amazon_ads.report_fetcher import SEARCH_TERM_SPEC, ReportFetcher, ReportSpec, SbV2ReportFetcher
from core.amazon_ads.sync_planner import (
    CAMPAIGN_CHUNK_DAYS,
    CAMPAIGNS_KIND,
    PRODUCT_CHUNK_DAYS,
    SB_CAMPAIGNS_KIND,
    SB_LEGACY_KIND,
    SB_LEGACY_SEARCH_TERMS_KIND,
    SB_SEARCH_TERMS_KIND,
    SB_TARGETING_KIND,
    SD_CAMPAIGNS_KIND,
    SD_TARGETING_KIND,
    SEARCH_TERMS_KIND,
    SP_TARGETING_KIND,
)

SEARCH_TERMS_REPORT = "search_terms"
CAMPAIGNS_REPORT = "campaigns"
SP_TARGETING_REPORT = "sp_targeting"
SB_CAMPAIGNS_REPORT = "sb_campaigns"
SB_TARGETING_REPORT = "sb_targeting"
SD_CAMPAIGNS_REPORT = "sd_campaigns"
SD_TARGETING_REPORT = "sd_targeting"
SB_LEGACY_REPORT = "sb_legacy_campaigns"
SB_SEARCH_TERMS_REPORT = "sb_search_terms"
SB_LEGACY_SEARCH_TERMS_REPORT = "sb_legacy_search_terms"


@dataclass(frozen=True)
class ReportKind:
    """One report the worker knows how to ingest, end to end."""

    name: str
    job_kind: str
    spec: ReportSpec
    replace_day_rpc: str
    load_compact_report: Callable
    day_row_positions: Callable
    day_rows: Callable
    # None asks for the adaptive rule that shrinks a heavy profile's chunks.
    chunk_days: int | None
    # A kind's own slice of a tick, so its chunks never delay another kind's saves; None = the worker's limit.
    max_inflight_reports: int | None = None
    max_creates_per_tick: int | None = None
    max_saves_per_tick: int | None = None
    # Constant arguments the replace RPC takes besides profile, day and rows, e.g. the ad product.
    rpc_args: dict = field(default_factory=dict)
    # How its reports are asked for and fetched: Reporting v3, unless the report is another API's.
    fetcher: type[ReportFetcher] = ReportFetcher


SEARCH_TERMS = ReportKind(
    name=SEARCH_TERMS_REPORT,
    job_kind=SEARCH_TERMS_KIND,
    spec=SEARCH_TERM_SPEC,
    replace_day_rpc="replace_search_term_day",
    load_compact_report=search_term_rows.load_compact_report,
    day_row_positions=search_term_rows.day_row_positions,
    day_rows=search_term_rows.day_rows,
    chunk_days=None,
)

CAMPAIGNS = ReportKind(
    name=CAMPAIGNS_REPORT,
    job_kind=CAMPAIGNS_KIND,
    spec=CAMPAIGN_REPORT_SPEC,
    replace_day_rpc="replace_campaign_day",
    load_compact_report=campaign_rows.load_compact_report,
    day_row_positions=campaign_rows.day_row_positions,
    day_rows=campaign_rows.day_rows,
    chunk_days=CAMPAIGN_CHUNK_DAYS,
    # Shared by every profile and kept small: each report counts against the same Amazon rate limit.
    max_inflight_reports=3,
    max_creates_per_tick=3,
    max_saves_per_tick=3,
)


def _product_kind(name: str, job_kind: str, spec: ReportSpec, parser, replace_day_rpc: str,
                  **rpc_args) -> ReportKind:
    # Each report of the new grains gets the same small slice as campaigns: they share Amazon's rate limit.
    return ReportKind(
        name=name,
        job_kind=job_kind,
        spec=spec,
        replace_day_rpc=replace_day_rpc,
        load_compact_report=parser.load_compact_report,
        day_row_positions=parser.day_row_positions,
        day_rows=parser.day_rows,
        chunk_days=PRODUCT_CHUNK_DAYS,
        max_inflight_reports=3,
        max_creates_per_tick=3,
        max_saves_per_tick=3,
        rpc_args=rpc_args,
    )


def _sb_v2(kind: ReportKind) -> ReportKind:
    """A v2 report is one day each, and its rows go to the day as the v2 source: they never erase v3's. A history is
    60 reports, most ready in a minute but some after ten: twice the slots keeps one slow day from holding the rest."""
    return dataclasses.replace(kind, chunk_days=1, fetcher=SbV2ReportFetcher,
                               rpc_args={**kind.rpc_args, "p_source": "v2"},
                               max_inflight_reports=6, max_creates_per_tick=6, max_saves_per_tick=6)


SP_TARGETING = _product_kind(SP_TARGETING_REPORT, SP_TARGETING_KIND, product_rows.SP_TARGETING_SPEC,
                             product_rows.SP_TARGETING_ROWS, "replace_target_day", p_ad_product="SP")
SD_CAMPAIGNS = _product_kind(SD_CAMPAIGNS_REPORT, SD_CAMPAIGNS_KIND, product_rows.SD_CAMPAIGN_SPEC,
                             product_rows.SD_CAMPAIGN_ROWS, "replace_sb_sd_campaign_day", p_ad_product="SD")
SD_TARGETING = _product_kind(SD_TARGETING_REPORT, SD_TARGETING_KIND, product_rows.SD_TARGETING_SPEC,
                             product_rows.SD_TARGETING_ROWS, "replace_target_day", p_ad_product="SD")
SB_CAMPAIGNS = _product_kind(SB_CAMPAIGNS_REPORT, SB_CAMPAIGNS_KIND, product_rows.SB_CAMPAIGN_SPEC,
                             product_rows.SB_CAMPAIGN_ROWS, "replace_sb_sd_campaign_day", p_ad_product="SB")
SB_TARGETING = _product_kind(SB_TARGETING_REPORT, SB_TARGETING_KIND, product_rows.SB_TARGETING_SPEC,
                             product_rows.SB_TARGETING_ROWS, "replace_target_day", p_ad_product="SB")
SB_LEGACY_CAMPAIGNS = _sb_v2(_product_kind(SB_LEGACY_REPORT, SB_LEGACY_KIND, product_rows.SB_LEGACY_CAMPAIGN_SPEC,
                                           product_rows.SB_LEGACY_CAMPAIGN_ROWS, "replace_sb_sd_campaign_day",
                                           p_ad_product="SB"))
# SB's search terms have a table of their own, so their day takes no ad product.
SB_SEARCH_TERMS = _product_kind(SB_SEARCH_TERMS_REPORT, SB_SEARCH_TERMS_KIND, product_rows.SB_SEARCH_TERM_SPEC,
                                product_rows.SB_SEARCH_TERM_ROWS, "replace_sb_search_term_day")
SB_LEGACY_SEARCH_TERMS = _sb_v2(_product_kind(SB_LEGACY_SEARCH_TERMS_REPORT, SB_LEGACY_SEARCH_TERMS_KIND,
                                              product_rows.SB_LEGACY_SEARCH_TERM_SPEC,
                                              product_rows.SB_LEGACY_SEARCH_TERM_ROWS, "replace_sb_search_term_day"))

# SP search terms go first: the agency's week depends on them.
ALL = (SEARCH_TERMS, CAMPAIGNS, SP_TARGETING, SD_CAMPAIGNS, SD_TARGETING, SB_CAMPAIGNS, SB_TARGETING,
       SB_LEGACY_CAMPAIGNS, SB_SEARCH_TERMS, SB_LEGACY_SEARCH_TERMS)
_BY_NAME = {kind.name: kind for kind in ALL}
_BY_JOB_KIND = {kind.job_kind: kind for kind in ALL}
REPORT_JOB_KINDS = tuple(_BY_JOB_KIND)


def by_name(name: str | None) -> ReportKind:
    """The kind a stored request belongs to; rows written before the column default to search terms."""
    return _BY_NAME.get(str(name or SEARCH_TERMS_REPORT), SEARCH_TERMS)


def by_job_kind(job_kind: str) -> ReportKind | None:
    return _BY_JOB_KIND.get(job_kind)

"""What differs between the Reporting v3 reports the worker ingests.

Requesting, polling, downloading and archiving are identical for every report, so they stay in
`ingestion_job`. Only the pieces below change, and they travel together: the columns asked for,
the mapper that reads exactly those columns, and the function that writes the day.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from core.amazon_ads import campaign_rows, search_term_rows
from core.amazon_ads.campaign_rows import CAMPAIGN_REPORT_SPEC
from core.amazon_ads.report_fetcher import SEARCH_TERM_SPEC, ReportSpec
from core.amazon_ads.sync_planner import CAMPAIGN_CHUNK_DAYS, CAMPAIGNS_KIND, SEARCH_TERMS_KIND

SEARCH_TERMS_REPORT = "search_terms"
CAMPAIGNS_REPORT = "campaigns"


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

# Search terms go first: the agency's week depends on them.
ALL = (SEARCH_TERMS, CAMPAIGNS)
_BY_NAME = {kind.name: kind for kind in ALL}
_BY_JOB_KIND = {kind.job_kind: kind for kind in ALL}
REPORT_JOB_KINDS = tuple(_BY_JOB_KIND)


def by_name(name: str | None) -> ReportKind:
    """The kind a stored request belongs to; rows written before the column default to search terms."""
    return _BY_NAME.get(str(name or SEARCH_TERMS_REPORT), SEARCH_TERMS)


def by_job_kind(job_kind: str) -> ReportKind | None:
    return _BY_JOB_KIND.get(job_kind)

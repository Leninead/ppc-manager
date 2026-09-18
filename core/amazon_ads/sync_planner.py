"""Which Amazon Ads sync jobs each profile needs now, judged on the profile's own local clock.

Pure: no I/O, so the calendar rules can be tested across time zones and DST changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.integrations.amazon_identity import SLUG
from core.integrations.sync_jobs import NewSyncJob, parse_date, parse_timestamp

DAILY_WINDOW_DAYS = 14
DEEP_WINDOW_DAYS = 42
BACKFILL_DAYS = 65
CHUNK_DAYS = 14
# Very large profiles get shorter reports, so a single save stays well inside the worker's memory limit.
HEAVY_ROWS_PER_DAY = 12_000
HEAVY_CHUNK_DAYS = 7
DAILY_START = time(3, 0)
RETRY_UNTIL = time(23, 0)
DATA_PROMISE = time(9, 0)
TIMEZONE_BY_REGION = {"NA": "America/Los_Angeles", "EU": "Europe/London", "FE": "Asia/Tokyo"}

SEARCH_TERMS_KIND = "sp_search_terms"
PORTFOLIOS_KIND = "portfolio_names"
CAMPAIGNS_KIND = "sp_campaigns"
CAMPAIGN_ENTITIES_KIND = "campaign_entities"
# Campaign reports are small enough to rewrite the whole window nightly: no backfill state to keep.
CAMPAIGN_WINDOW_DAYS = 65
CAMPAIGN_CHUNK_DAYS = 31
CAMPAIGN_MAX_ATTEMPTS = 6

# Targeting of the three ad products, and Sponsored Brands / Sponsored Display campaigns.
SP_TARGETS_KIND = "sp_targets"
SB_ENTITIES_KIND = "sb_entities"
SD_ENTITIES_KIND = "sd_entities"
SP_TARGETING_KIND = "sp_targeting"
SB_CAMPAIGNS_KIND = "sb_campaigns"
SB_TARGETING_KIND = "sb_targeting"
SD_CAMPAIGNS_KIND = "sd_campaigns"
SD_TARGETING_KIND = "sd_targeting"
# SB campaigns of the old format, from the v2 report: v3's SB reports leave them out while in preview.
SB_LEGACY_KIND = "sb_legacy_campaigns"
PRODUCT_ENTITY_KINDS = (SP_TARGETS_KIND, SB_ENTITIES_KIND, SD_ENTITIES_KIND)
# The requests that write SB and SD campaign days: whatever reads those campaigns reads again after one.
PRODUCT_CAMPAIGN_KINDS = (SB_CAMPAIGNS_KIND, SD_CAMPAIGNS_KIND, SB_LEGACY_KIND)
# After a profile's history is in, each night asks only the last days, like the search terms do: five
# reports of 65 days every night for every profile would not fit in a day at 3 reports in flight.
PRODUCT_DAILY_WINDOW_DAYS = 14
PRODUCT_CHUNK_DAYS = 31


@dataclass(frozen=True)
class ProductReportPlan:
    """How one of the new reports is planned: its history, and the entity list it waits for."""

    job_kind: str
    history_days: int
    # SB and SD reports wait for that day's entity list and are skipped when it found no campaigns:
    # an account without the program would fail every night otherwise.
    entity_kind: str | None
    # Only for a profile whose SB list still has campaigns of the old format.
    needs_legacy_sb: bool = False


PRODUCT_REPORTS = (
    ProductReportPlan(SP_TARGETING_KIND, history_days=65, entity_kind=None),
    ProductReportPlan(SD_CAMPAIGNS_KIND, history_days=65, entity_kind=SD_ENTITIES_KIND),
    ProductReportPlan(SD_TARGETING_KIND, history_days=65, entity_kind=SD_ENTITIES_KIND),
    # Amazon keeps Sponsored Brands report data for 60 days only.
    ProductReportPlan(SB_CAMPAIGNS_KIND, history_days=60, entity_kind=SB_ENTITIES_KIND),
    ProductReportPlan(SB_TARGETING_KIND, history_days=60, entity_kind=SB_ENTITIES_KIND),
    ProductReportPlan(SB_LEGACY_KIND, history_days=60, entity_kind=SB_ENTITIES_KIND, needs_legacy_sb=True),
)
PRODUCT_REPORT_KINDS = tuple(plan.job_kind for plan in PRODUCT_REPORTS)
PRODUCT_KINDS = PRODUCT_ENTITY_KINDS + PRODUCT_REPORT_KINDS
_HISTORY_DAYS = {plan.job_kind: plan.history_days for plan in PRODUCT_REPORTS}
PROFILE_ACTIVE = "active"
PROFILE_NEEDS_REAUTH = "needs_reauth"
PROFILE_INACTIVE = "inactive"
BACKFILL_MAX_ATTEMPTS = 6
DAILY_MAX_ATTEMPTS = 8
PORTFOLIO_MAX_ATTEMPTS = 3
BACKFILL_DEADLINE = timedelta(hours=24)
# Attribution and invalid-click corrections can land weeks late; one wider pass a week rewrites them.
DEEP_REFRESH_ISOWEEKDAY = 7
_FALLBACK_TIMEZONE = TIMEZONE_BY_REGION["NA"]


@dataclass(frozen=True)
class ProfileState:
    profile_id: str
    account_id: int | None
    connection_id: int | None
    cliente: str
    account_name: str
    account_type: str
    region: str
    country_code: str
    currency_code: str
    timezone: str
    status: str
    backfill_done_at: datetime | None
    refreshed_on: date | None
    has_open_backfill: bool = False
    has_open_day_job_today: bool = False
    has_portfolio_job_today: bool = False
    has_campaign_job_today: bool = False
    has_campaign_entities_job_today: bool = False
    # The new kinds, by job kind: planned today (open, or closed still holding today's dedupe key),
    # open on any day, history already loaded, and rows of each entity list completed today.
    product_kinds_today: frozenset[str] = frozenset()
    product_kinds_open: frozenset[str] = frozenset()
    product_histories_done: frozenset[str] = frozenset()
    entity_rows_today: dict = field(default_factory=dict)
    # The SB list still has campaigns of the old format (isMultiAdGroupsEnabled = false), which only v2 reports.
    has_legacy_sb: bool = False

    @classmethod
    def from_row(cls, row: dict, *, has_open_backfill: bool = False, has_open_day_job_today: bool = False,
                 has_portfolio_job_today: bool = False, has_campaign_job_today: bool = False,
                 has_campaign_entities_job_today: bool = False, product_kinds_today: frozenset[str] = frozenset(),
                 product_kinds_open: frozenset[str] = frozenset(),
                 product_histories_done: frozenset[str] = frozenset(),
                 entity_rows_today: dict | None = None, has_legacy_sb: bool = False) -> ProfileState:
        """From an `ads_profile_sync` row plus what the job queue says about the profile."""
        return cls(
            profile_id=str(row["profile_id"]),
            account_id=_optional_int(row.get("account_id")),
            connection_id=_optional_int(row.get("connection_id")),
            cliente=row.get("cliente") or "",
            account_name=row.get("account_name") or "",
            account_type=row.get("account_type") or "",
            region=row.get("region") or "",
            country_code=row.get("country_code") or "",
            currency_code=row.get("currency_code") or "",
            timezone=row.get("timezone") or "",
            status=row.get("status") or "",
            backfill_done_at=parse_timestamp(row.get("backfill_done_at")),
            refreshed_on=parse_date(row.get("refreshed_on")),
            has_open_backfill=has_open_backfill,
            has_open_day_job_today=has_open_day_job_today,
            has_portfolio_job_today=has_portfolio_job_today,
            has_campaign_job_today=has_campaign_job_today,
            has_campaign_entities_job_today=has_campaign_entities_job_today,
            product_kinds_today=product_kinds_today,
            product_kinds_open=product_kinds_open,
            product_histories_done=product_histories_done,
            entity_rows_today=dict(entity_rows_today or {}),
            has_legacy_sb=has_legacy_sb,
        )


def profile_timezone(timezone: str, region: str) -> ZoneInfo:
    """The profile's zone; an empty or unknown one falls back to its region's marketplace zone."""
    for candidate in (timezone, TIMEZONE_BY_REGION.get(region, "")):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo(_FALLBACK_TIMEZONE)


def profile_local_now(state: ProfileState, now_utc: datetime) -> datetime:
    return now_utc.astimezone(profile_timezone(state.timezone, state.region))


def plan_jobs(state: ProfileState, now_utc: datetime) -> list[NewSyncJob]:
    """Backfill first; daily or Sunday-deep refreshes only once the backfill is done.

    A day job is planned between 03:00 and 23:00 local: later, its deadline would already be gone.
    """
    if state.status != PROFILE_ACTIVE:
        return []
    local_now = profile_local_now(state, now_utc)
    local_today = local_now.date()
    before_cutoff = local_now.time() < RETRY_UNTIL
    after_start = local_now.time() >= DAILY_START

    planned: list[NewSyncJob] = []
    planning_backfill = state.backfill_done_at is None and not state.has_open_backfill
    if planning_backfill:
        planned.append(backfill_job(state, now_utc))
    elif (
        state.backfill_done_at is not None
        and after_start
        and before_cutoff
        and (state.refreshed_on is None or state.refreshed_on < local_today)
        and not state.has_open_day_job_today
    ):
        planned.append(_day_job(state, local_now))

    if not state.has_portfolio_job_today and before_cutoff and (planning_backfill or after_start):
        planned.append(_portfolio_job(state, local_now))

    # The campaign grain does not wait for the search-term backfill: M6 and M8 read it on its own.
    if after_start and before_cutoff:
        if not state.has_campaign_entities_job_today:
            planned.append(_campaign_entities_job(state, local_now))
        if not state.has_campaign_job_today:
            planned.append(_campaign_job(state, local_now))
        planned.extend(_product_jobs(state, local_now, now_utc))
    return planned


def _product_jobs(state: ProfileState, local_now: datetime, now_utc: datetime) -> list[NewSyncJob]:
    """Targeting of the three ad products and SB / SD campaigns: an entity list per product every day,
    and each report's history once, then only the last days every night."""
    planned = []
    busy = state.product_kinds_today | state.product_kinds_open
    for entity_kind in PRODUCT_ENTITY_KINDS:
        if entity_kind not in busy:
            planned.append(_entity_list_job(state, local_now, entity_kind))
    for plan in PRODUCT_REPORTS:
        if plan.job_kind in busy:
            continue
        if plan.entity_kind is not None and int(state.entity_rows_today.get(plan.entity_kind) or 0) <= 0:
            continue
        if plan.needs_legacy_sb and not state.has_legacy_sb:
            continue
        if plan.job_kind in state.product_histories_done:
            planned.append(_product_day_job(state, local_now, plan))
        else:
            planned.append(_product_history_job(state, local_now, now_utc, plan))
    return planned


def is_product_history(job_kind: str, window_start: date | None, window_end: date | None) -> bool:
    """Whether a job of the new report kinds covered that report's whole history (retries keep the window)."""
    history_days = _HISTORY_DAYS.get(job_kind)
    if history_days is None or window_start is None or window_end is None:
        return False
    return (window_end - window_start).days + 1 >= history_days


def backfill_job(state: ProfileState, now_utc: datetime) -> NewSyncJob:
    local_today = profile_local_now(state, now_utc).date()
    yesterday = local_today - timedelta(days=1)
    return _new_job(
        state,
        job_kind=SEARCH_TERMS_KIND,
        trigger="backfill",
        window_start=yesterday - timedelta(days=BACKFILL_DAYS - 1),
        window_end=yesterday,
        local_day=local_today,
        deadline_at=now_utc.astimezone(timezone.utc) + BACKFILL_DEADLINE,
        max_attempts=BACKFILL_MAX_ATTEMPTS,
        dedupe_key=backfill_dedupe_key(state.profile_id, local_today),
    )


def backfill_dedupe_key(profile_id: str, local_day: date) -> str:
    """Scoped to the profile's day: a failed or cancelled backfill is planned again at most once a day."""
    return f"{backfill_dedupe_prefix(profile_id)}{local_day.isoformat()}"


def backfill_dedupe_prefix(profile_id: str) -> str:
    return f"{SLUG}:{profile_id}:backfill:"


def is_backfill(trigger: str, window_start: date | None, window_end: date | None) -> bool:
    """A retry of a backfill keeps the backfill's window, not its trigger."""
    if trigger == "backfill":
        return True
    return window_start is not None and window_end is not None and (window_end - window_start).days + 1 >= BACKFILL_DAYS


def chunk_days_for(rows_per_day: float) -> int:
    return HEAVY_CHUNK_DAYS if rows_per_day > HEAVY_ROWS_PER_DAY else CHUNK_DAYS


def report_chunks(start: date, end: date, max_days: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    """Newest chunk first, so the days people look at land before the old ones."""
    if max_days < 1:
        raise ValueError(f"chunks need at least one day, got {max_days}")
    if end < start:
        raise ValueError(f"window ends before it starts: {start}..{end}")
    chunks = []
    chunk_end = end
    while chunk_end >= start:
        chunk_start = max(start, chunk_end - timedelta(days=max_days - 1))
        chunks.append((chunk_start, chunk_end))
        chunk_end = chunk_start - timedelta(days=1)
    return chunks


def _day_job(state: ProfileState, local_now: datetime) -> NewSyncJob:
    local_today = local_now.date()
    is_deep = local_today.isoweekday() == DEEP_REFRESH_ISOWEEKDAY
    window_days = DEEP_WINDOW_DAYS if is_deep else DAILY_WINDOW_DAYS
    yesterday = local_today - timedelta(days=1)
    return _new_job(
        state,
        job_kind=SEARCH_TERMS_KIND,
        trigger="scheduled_deep" if is_deep else "scheduled_daily",
        window_start=yesterday - timedelta(days=window_days - 1),
        window_end=yesterday,
        local_day=local_today,
        deadline_at=_local_cutoff_utc(local_now),
        max_attempts=DAILY_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:day:{local_today.isoformat()}",
    )


def _portfolio_job(state: ProfileState, local_now: datetime) -> NewSyncJob:
    local_today = local_now.date()
    return _new_job(
        state,
        job_kind=PORTFOLIOS_KIND,
        trigger="scheduled_daily",
        window_start=None,
        window_end=None,
        local_day=local_today,
        deadline_at=_local_cutoff_utc(local_now),
        max_attempts=PORTFOLIO_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:portfolios:{local_today.isoformat()}",
    )


def _campaign_job(state: ProfileState, local_now: datetime) -> NewSyncJob:
    local_today = local_now.date()
    yesterday = local_today - timedelta(days=1)
    return _new_job(
        state,
        job_kind=CAMPAIGNS_KIND,
        trigger="scheduled_daily",
        window_start=yesterday - timedelta(days=CAMPAIGN_WINDOW_DAYS - 1),
        window_end=yesterday,
        local_day=local_today,
        deadline_at=_local_cutoff_utc(local_now),
        max_attempts=CAMPAIGN_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:campaigns:{local_today.isoformat()}",
    )


def _campaign_entities_job(state: ProfileState, local_now: datetime) -> NewSyncJob:
    local_today = local_now.date()
    return _new_job(
        state,
        job_kind=CAMPAIGN_ENTITIES_KIND,
        trigger="scheduled_daily",
        window_start=None,
        window_end=None,
        local_day=local_today,
        deadline_at=_local_cutoff_utc(local_now),
        max_attempts=PORTFOLIO_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:campaign-entities:{local_today.isoformat()}",
    )


def _entity_list_job(state: ProfileState, local_now: datetime, job_kind: str) -> NewSyncJob:
    local_today = local_now.date()
    return _new_job(
        state,
        job_kind=job_kind,
        trigger="scheduled_daily",
        window_start=None,
        window_end=None,
        local_day=local_today,
        deadline_at=_local_cutoff_utc(local_now),
        max_attempts=PORTFOLIO_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:{job_kind}:{local_today.isoformat()}",
    )


def _product_day_job(state: ProfileState, local_now: datetime, plan: ProductReportPlan) -> NewSyncJob:
    local_today = local_now.date()
    yesterday = local_today - timedelta(days=1)
    return _new_job(
        state,
        job_kind=plan.job_kind,
        trigger="scheduled_daily",
        window_start=yesterday - timedelta(days=PRODUCT_DAILY_WINDOW_DAYS - 1),
        window_end=yesterday,
        local_day=local_today,
        deadline_at=_local_cutoff_utc(local_now),
        max_attempts=CAMPAIGN_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:{plan.job_kind}:{local_today.isoformat()}",
    )


def _product_history_job(state: ProfileState, local_now: datetime, now_utc: datetime,
                         plan: ProductReportPlan) -> NewSyncJob:
    local_today = local_now.date()
    yesterday = local_today - timedelta(days=1)
    return _new_job(
        state,
        job_kind=plan.job_kind,
        trigger="backfill",
        window_start=yesterday - timedelta(days=plan.history_days - 1),
        window_end=yesterday,
        local_day=local_today,
        # A first load of every profile queues many chunks at 3 in flight: a day is not enough.
        deadline_at=now_utc.astimezone(timezone.utc) + BACKFILL_DEADLINE,
        max_attempts=CAMPAIGN_MAX_ATTEMPTS,
        dedupe_key=f"{SLUG}:{state.profile_id}:{plan.job_kind}-history:{local_today.isoformat()}",
    )


def _new_job(state: ProfileState, *, job_kind: str, trigger: str, window_start: date | None,
             window_end: date | None, local_day: date, deadline_at: datetime, max_attempts: int,
             dedupe_key: str) -> NewSyncJob:
    return NewSyncJob(
        integration_slug=SLUG,
        job_kind=job_kind,
        trigger=trigger,
        external_account_id=state.profile_id,
        account_id=state.account_id,
        connection_id=state.connection_id,
        cliente=state.cliente,
        account_name=state.account_name,
        marketplace=state.country_code,
        region=state.region,
        window_start=window_start,
        window_end=window_end,
        local_day=local_day,
        deadline_at=deadline_at,
        max_attempts=max_attempts,
        dedupe_key=dedupe_key,
    )


def _local_cutoff_utc(local_now: datetime) -> datetime:
    return datetime.combine(local_now.date(), RETRY_UNTIL, tzinfo=local_now.tzinfo).astimezone(timezone.utc)


def _optional_int(raw) -> int | None:
    return int(raw) if raw is not None else None

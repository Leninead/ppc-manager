"""Sync planner: local-time scheduling across time zones and DST changes. Pure, no I/O."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from core.amazon_ads.sync_planner import (
    CAMPAIGN_ENTITIES_KIND,
    CAMPAIGNS_KIND,
    PORTFOLIOS_KIND,
    SEARCH_TERMS_KIND,
    ProfileState,
    backfill_dedupe_key,
    chunk_days_for,
    is_backfill,
    plan_jobs,
    profile_local_now,
    profile_timezone,
    report_chunks,
)

LOS_ANGELES = ZoneInfo("America/Los_Angeles")
BACKFILL_DONE = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _state(**overrides) -> ProfileState:
    state = ProfileState(
        profile_id="p-100", account_id=7, connection_id=3, cliente="cliente-demo", account_name="Demo Seller",
        account_type="seller", region="NA", country_code="US", currency_code="USD",
        timezone="America/Los_Angeles", status="active", backfill_done_at=BACKFILL_DONE, refreshed_on=None,
    )
    return replace(state, **overrides)


def _utc(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _kinds(planned) -> list[tuple[str, str]]:
    return [(job.job_kind, job.trigger) for job in planned]


def _search_terms_job(planned):
    matches = [job for job in planned if job.job_kind == SEARCH_TERMS_KIND]
    assert len(matches) == 1, planned
    return matches[0]


def test_weekday_after_three_am_plans_a_fourteen_day_daily_job_ending_yesterday():
    now = _utc(2026, 9, 14, 17)  # Monday 10:00 PDT

    planned = plan_jobs(_state(), now)

    assert _kinds(planned) == [(SEARCH_TERMS_KIND, "scheduled_daily"), (PORTFOLIOS_KIND, "scheduled_daily"),
                               (CAMPAIGN_ENTITIES_KIND, "scheduled_daily"), (CAMPAIGNS_KIND, "scheduled_daily")]
    daily = planned[0]
    assert (daily.window_start, daily.window_end) == (date(2026, 8, 31), date(2026, 9, 13))
    assert daily.local_day == date(2026, 9, 14)
    assert daily.max_attempts == 8
    assert daily.dedupe_key == "amazon_ads:p-100:day:2026-09-14"
    assert daily.deadline_at == _utc(2026, 9, 15, 6)  # 23:00 PDT
    assert (daily.marketplace, daily.region, daily.connection_id) == ("US", "NA", 3)
    portfolios = planned[1]
    assert portfolios.dedupe_key == "amazon_ads:p-100:portfolios:2026-09-14"
    assert (portfolios.window_start, portfolios.window_end, portfolios.max_attempts) == (None, None, 3)


def test_before_three_am_local_nothing_daily_is_planned():
    now = _utc(2026, 9, 14, 9, 59)  # 02:59 PDT

    assert plan_jobs(_state(), now) == []


def test_exactly_three_am_local_is_already_due():
    now = _utc(2026, 9, 14, 10)  # 03:00 PDT

    assert _search_terms_job(plan_jobs(_state(), now)).trigger == "scheduled_daily"


def test_after_the_retry_cutoff_no_born_dead_job_is_planned():
    now = _utc(2026, 9, 15, 6, 30)  # 23:30 PDT on the 14th

    assert plan_jobs(_state(), now) == []


def test_sunday_plans_the_deep_forty_two_day_refresh():
    now = _utc(2026, 9, 13, 16)  # Sunday 09:00 PDT

    deep = _search_terms_job(plan_jobs(_state(), now))

    assert deep.trigger == "scheduled_deep"
    assert (deep.window_start, deep.window_end) == (date(2026, 8, 2), date(2026, 9, 12))
    assert (deep.window_end - deep.window_start).days + 1 == 42
    assert deep.dedupe_key == "amazon_ads:p-100:day:2026-09-13"


def test_spring_forward_day_uses_pacific_daylight_time_for_start_and_deadline():
    # 2026-03-08 is a Sunday: 02:00 PST jumps to 03:00 PDT at 10:00 UTC.
    assert plan_jobs(_state(), _utc(2026, 3, 8, 9, 59)) == []

    deep = _search_terms_job(plan_jobs(_state(), _utc(2026, 3, 8, 10)))

    assert deep.trigger == "scheduled_deep"
    assert deep.local_day == date(2026, 3, 8)
    assert deep.window_end == date(2026, 3, 7)
    assert deep.deadline_at == _utc(2026, 3, 9, 6)  # 23:00 PDT = UTC-7


def test_fall_back_day_uses_pacific_standard_time_for_start_and_deadline():
    # 2026-11-01 is a Sunday: 02:00 PDT falls back to 01:00 PST at 09:00 UTC.
    assert plan_jobs(_state(), _utc(2026, 11, 1, 10, 59)) == []  # 02:59 PST

    deep = _search_terms_job(plan_jobs(_state(), _utc(2026, 11, 1, 11)))

    assert deep.local_day == date(2026, 11, 1)
    assert deep.deadline_at == _utc(2026, 11, 2, 7)  # 23:00 PST = UTC-8


def test_local_day_follows_the_profile_not_utc():
    now = _utc(2026, 9, 15, 2)  # already the 15th in UTC, still 19:00 on the 14th in Los Angeles

    daily = _search_terms_job(plan_jobs(_state(), now))

    assert daily.local_day == date(2026, 9, 14)
    assert daily.window_end == date(2026, 9, 13)


def test_refreshed_today_or_open_day_job_plans_no_day_job():
    now = _utc(2026, 9, 14, 17)

    assert _kinds(plan_jobs(_state(refreshed_on=date(2026, 9, 14)), now)) == [
        (PORTFOLIOS_KIND, "scheduled_daily"), (CAMPAIGN_ENTITIES_KIND, "scheduled_daily"), (CAMPAIGNS_KIND, "scheduled_daily")]
    assert plan_jobs(_state(has_open_day_job_today=True, has_portfolio_job_today=True,
                            has_campaign_job_today=True, has_campaign_entities_job_today=True), now) == []


def test_refreshed_yesterday_is_due_again_today():
    now = _utc(2026, 9, 14, 17)

    assert _search_terms_job(plan_jobs(_state(refreshed_on=date(2026, 9, 13)), now)).trigger == "scheduled_daily"


def test_backfill_takes_precedence_over_the_daily_job():
    now = _utc(2026, 9, 14, 17)

    planned = plan_jobs(_state(backfill_done_at=None), now)

    assert _kinds(planned) == [(SEARCH_TERMS_KIND, "backfill"), (PORTFOLIOS_KIND, "scheduled_daily"),
                               (CAMPAIGN_ENTITIES_KIND, "scheduled_daily"), (CAMPAIGNS_KIND, "scheduled_daily")]
    backfill = planned[0]
    assert (backfill.window_start, backfill.window_end) == (date(2026, 7, 11), date(2026, 9, 13))
    assert (backfill.window_end - backfill.window_start).days + 1 == 65
    assert backfill.max_attempts == 6
    assert backfill.deadline_at == now + timedelta(hours=24)
    assert backfill.dedupe_key == backfill_dedupe_key("p-100", date(2026, 9, 14))
    assert backfill.dedupe_key == "amazon_ads:p-100:backfill:2026-09-14"


def test_backfill_key_follows_the_profile_local_day_not_utc():
    now = _utc(2026, 9, 15, 2)  # the 15th in UTC, still the 14th in Los Angeles

    backfill = _search_terms_job(plan_jobs(_state(backfill_done_at=None), now))

    assert backfill.dedupe_key == "amazon_ads:p-100:backfill:2026-09-14"


@pytest.mark.parametrize("rows_per_day, expected_days", [(0, 14), (12_000, 14), (12_000.5, 7), (40_000, 7)])
def test_chunks_shrink_to_seven_days_only_above_twelve_thousand_rows_a_day(rows_per_day, expected_days):
    assert chunk_days_for(rows_per_day) == expected_days


@pytest.mark.parametrize("trigger, window_start, window_end, expected", [
    ("backfill", None, None, True),
    ("retry", date(2026, 7, 11), date(2026, 9, 13), True),
    ("retry", date(2026, 8, 31), date(2026, 9, 13), False),
    ("manual", None, None, False),
])
def test_a_backfill_is_recognized_by_its_trigger_or_its_window(trigger, window_start, window_end, expected):
    assert is_backfill(trigger, window_start, window_end) is expected


def test_backfill_is_planned_at_any_hour_with_its_portfolio_job():
    now = _utc(2026, 9, 14, 8)  # 01:00 PDT, before the daily start

    assert _kinds(plan_jobs(_state(backfill_done_at=None), now)) == [
        (SEARCH_TERMS_KIND, "backfill"), (PORTFOLIOS_KIND, "scheduled_daily")]


def test_while_the_backfill_runs_no_daily_job_is_planned():
    now = _utc(2026, 9, 14, 17)

    planned = plan_jobs(_state(backfill_done_at=None, has_open_backfill=True), now)

    assert _kinds(planned) == [(PORTFOLIOS_KIND, "scheduled_daily"), (CAMPAIGN_ENTITIES_KIND, "scheduled_daily"), (CAMPAIGNS_KIND, "scheduled_daily")]


def test_inactive_or_reauth_profiles_plan_nothing():
    now = _utc(2026, 9, 14, 17)

    assert plan_jobs(_state(status="needs_reauth"), now) == []
    assert plan_jobs(_state(status="inactive", backfill_done_at=None), now) == []


def test_eu_profile_without_timezone_falls_back_to_london():
    state = _state(timezone="", region="EU", country_code="UK")
    now = _utc(2026, 9, 14, 2)  # 03:00 BST

    assert profile_timezone("", "EU") == ZoneInfo("Europe/London")
    assert profile_local_now(state, now).hour == 3
    daily = _search_terms_job(plan_jobs(state, now))
    assert daily.deadline_at == _utc(2026, 9, 14, 22)  # 23:00 BST


def test_fe_profile_with_unknown_timezone_falls_back_to_tokyo():
    state = _state(timezone="Not/AZone", region="FE", country_code="JP")
    now = _utc(2026, 9, 13, 18)  # 03:00 on Monday the 14th in Tokyo

    assert profile_timezone("Not/AZone", "FE") == ZoneInfo("Asia/Tokyo")
    daily = _search_terms_job(plan_jobs(state, now))
    assert daily.local_day == date(2026, 9, 14)
    assert daily.deadline_at == _utc(2026, 9, 14, 14)  # 23:00 JST


def test_profile_without_timezone_or_known_region_uses_los_angeles():
    assert profile_timezone("", "") == LOS_ANGELES


def test_from_row_parses_dates_and_carries_queue_flags():
    state = ProfileState.from_row(
        {"profile_id": 555, "account_id": "7", "connection_id": None, "status": "active",
         "backfill_done_at": "2026-09-01T10:00:00+00:00", "refreshed_on": "2026-09-13", "timezone": None},
        has_open_backfill=True,
    )

    assert state.profile_id == "555" and state.account_id == 7 and state.connection_id is None
    assert state.backfill_done_at == _utc(2026, 9, 1, 10)
    assert state.refreshed_on == date(2026, 9, 13)
    assert state.timezone == "" and state.has_open_backfill is True


def test_backfill_window_splits_into_five_chunks_newest_first():
    chunks = report_chunks(date(2026, 7, 11), date(2026, 9, 13))

    assert chunks == [
        (date(2026, 8, 31), date(2026, 9, 13)),
        (date(2026, 8, 17), date(2026, 8, 30)),
        (date(2026, 8, 3), date(2026, 8, 16)),
        (date(2026, 7, 20), date(2026, 8, 2)),
        (date(2026, 7, 11), date(2026, 7, 19)),
    ]
    assert all((end - start).days + 1 <= 14 for start, end in chunks)


def test_chunks_cover_the_window_exactly_once():
    start, end = date(2026, 8, 1), date(2026, 9, 11)
    days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    chunks = report_chunks(start, end)

    assert len(chunks) == 3
    covered = sorted(day for chunk_start, chunk_end in chunks for day in days if chunk_start <= day <= chunk_end)
    assert covered == days


def test_single_day_window_is_one_chunk():
    assert report_chunks(date(2026, 9, 13), date(2026, 9, 13)) == [(date(2026, 9, 13), date(2026, 9, 13))]


@pytest.mark.parametrize("start, end, max_days", [
    (date(2026, 9, 14), date(2026, 9, 13), 14),
    (date(2026, 9, 1), date(2026, 9, 13), 0),
])
def test_invalid_chunk_requests_raise(start, end, max_days):
    with pytest.raises(ValueError):
        report_chunks(start, end, max_days)


def _campaign_job(planned):
    matches = [job for job in planned if job.job_kind == CAMPAIGNS_KIND]
    assert len(matches) == 1, planned
    return matches[0]


def test_the_campaign_window_is_sixty_five_days_ending_yesterday():
    now = _utc(2026, 9, 14, 17)  # Monday 10:00 PDT

    job = _campaign_job(plan_jobs(_state(), now))

    assert (job.window_start, job.window_end) == (date(2026, 7, 11), date(2026, 9, 13))
    assert job.local_day == date(2026, 9, 14)
    assert job.dedupe_key == "amazon_ads:p-100:campaigns:2026-09-14"


def test_the_campaign_grain_does_not_wait_for_the_search_term_backfill():
    now = _utc(2026, 9, 14, 17)

    planned = plan_jobs(_state(backfill_done_at=None, has_open_backfill=True), now)

    assert CAMPAIGNS_KIND in [job.job_kind for job in planned]
    assert CAMPAIGN_ENTITIES_KIND in [job.job_kind for job in planned]


def test_a_campaign_job_already_open_today_is_not_planned_again():
    now = _utc(2026, 9, 14, 17)

    planned = plan_jobs(_state(has_campaign_job_today=True, has_campaign_entities_job_today=True), now)

    assert CAMPAIGNS_KIND not in [job.job_kind for job in planned]
    assert CAMPAIGN_ENTITIES_KIND not in [job.job_kind for job in planned]


def test_campaign_jobs_wait_for_the_local_morning_like_the_daily_job():
    before_start = _utc(2026, 9, 14, 9)  # 02:00 PDT

    planned = plan_jobs(_state(), before_start)

    assert CAMPAIGNS_KIND not in [job.job_kind for job in planned]
    assert CAMPAIGN_ENTITIES_KIND not in [job.job_kind for job in planned]


def test_the_entities_snapshot_carries_no_window_because_it_is_a_photo():
    now = _utc(2026, 9, 14, 17)

    entities = [job for job in plan_jobs(_state(), now) if job.job_kind == CAMPAIGN_ENTITIES_KIND][0]

    assert (entities.window_start, entities.window_end) == (None, None)
    assert entities.dedupe_key == "amazon_ads:p-100:campaign-entities:2026-09-14"

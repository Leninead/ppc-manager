"""Calendar weeks and months of a window, and the day an activity started."""
from __future__ import annotations

from datetime import date

import pytest

from services.mcp_server.tools.period_series import (
    CalendarPeriod,
    activity_payload,
    activity_start,
    check_granularity,
    coverage,
    period_fields,
    period_of,
    periods_back,
    periods_within,
)


def test_a_week_runs_from_monday_to_sunday_and_a_month_is_the_calendar_one():
    assert period_of(date(2026, 9, 16), "week") == CalendarPeriod(date(2026, 9, 14), date(2026, 9, 20))
    assert period_of(date(2026, 9, 14), "week") == CalendarPeriod(date(2026, 9, 14), date(2026, 9, 20))
    assert period_of(date(2026, 2, 10), "month") == CalendarPeriod(date(2026, 2, 1), date(2026, 2, 28))
    assert period_of(date(2026, 12, 31), "month") == CalendarPeriod(date(2026, 12, 1), date(2026, 12, 31))


def test_the_last_periods_end_with_the_one_that_holds_the_last_day():
    """#12 asked for eleven calls, one per week: the periods now come from one."""
    weeks = periods_back(date(2026, 9, 16), "week", 3)

    assert [(week.start.isoformat(), week.end.isoformat()) for week in weeks] == [
        ("2026-08-31", "2026-09-06"), ("2026-09-07", "2026-09-13"), ("2026-09-14", "2026-09-20")]
    assert [month.start.isoformat() for month in periods_back(date(2026, 1, 5), "month", 2)] == [
        "2025-12-01", "2026-01-01"]


def test_the_periods_of_a_window_are_every_one_it_touches():
    months = periods_within(date(2026, 7, 20), date(2026, 9, 16), "month")

    assert [month.start.isoformat() for month in months] == ["2026-07-01", "2026-08-01", "2026-09-01"]


def test_a_period_the_data_does_not_cover_whole_is_not_complete():
    september = period_of(date(2026, 9, 1), "month")

    assert coverage(september, date(2026, 7, 20), date(2026, 9, 16)) == (16, False)
    assert period_fields(period_of(date(2026, 8, 1), "month"), date(2026, 7, 20), date(2026, 9, 16)) == {
        "period_start": "2026-08-01", "period_end": "2026-08-31", "days": 31, "days_with_data": 31, "complete": True}


def test_an_unknown_granularity_is_refused():
    with pytest.raises(ValueError, match="day, week o month"):
        check_granularity("quarter")


def test_the_first_day_and_the_current_run_come_from_the_days_read():
    values = [(date(2026, 9, day), clicks) for day, clicks in ((1, 0), (2, 3), (3, 0), (4, 5), (5, 2))]

    start = activity_start(values)

    assert (start.first_day, start.streak_start) == (date(2026, 9, 2), date(2026, 9, 4))
    assert activity_start([(date(2026, 9, 1), 4), (date(2026, 9, 2), 0)]).streak_start is None


def test_an_activity_on_the_first_day_read_may_have_started_before_it():
    """«Por primera vez el 1/9» was said of a campaign that had spent since before the days read."""
    payload = activity_payload(date(2026, 9, 1), {
        "clicks": [(date(2026, 9, 1), 2), (date(2026, 9, 2), 1)],
        "spend": [(date(2026, 9, 1), 0.0), (date(2026, 9, 2), 1.5)]})

    assert payload == {"read_from": "2026-09-01",
                       "clicks": {"first_day": "2026-09-01", "streak_start": "2026-09-01", "reaches_read_start": True},
                       "spend": {"first_day": "2026-09-02", "streak_start": "2026-09-02",
                                 "reaches_read_start": False}}

"""The periods Amazon reports Search Query Performance by: a week from Sunday to Saturday, or a calendar month."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

WEEK = "week"
MONTH = "month"

_SUNDAY = 6


@dataclass(frozen=True)
class SqpPeriod:
    period_type: str
    start: date
    end: date


def sqp_week(day: date) -> SqpPeriod:
    """The Sunday-to-Saturday week that holds the day."""
    start = day - timedelta(days=(day.weekday() - _SUNDAY) % 7)
    return SqpPeriod(WEEK, start, start + timedelta(days=6))


def sqp_month(day: date) -> SqpPeriod:
    """The calendar month that holds the day."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return SqpPeriod(MONTH, day.replace(day=1), day.replace(day=last_day))

"""The calendar periods a series is summed into, and the day an activity started.

A week starts on Monday; a month is a calendar month. A period the account does not have whole —the one in course,
or one cut by the start of its synced history or by the window asked for— says so in `complete`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Granularity = Literal["day", "week", "month"]
Period = Literal["", "week", "month"]
GRANULARITIES = ("day", "week", "month")
MAX_PERIODS = {"day": 60, "week": 26, "month": 12}
DEFAULT_PERIODS = {"day": 14, "week": 8, "month": 3}
# The longest window each granularity can read, in days.
MAX_WINDOW_DAYS = {"day": 60, "week": 26 * 7, "month": 366}
PERIOD_NOTE = ("Cada fila suma un período de calendario: la semana va de lunes a domingo y el mes es el del "
               "calendario. days es cuántos días tiene el período, days_with_data cuántos de ellos tienen datos "
               "sincronizados dentro de lo pedido y complete dice si están todos: un período en curso, o cortado por "
               "el inicio de la historia de la cuenta (data_since), no se compara como si fuera entero.")
ACTIVITY_NOTE = ("first_day es el primer día con clicks (o con gasto) desde read_from, y streak_start el primero de la "
                 "racha de días seguidos con clicks (o con gasto) que llega al último día leído; vacío si ese día no "
                 "tuvo. Con reaches_read_start en true la actividad ya estaba el primer día leído: pudo empezar antes, "
                 "así que no digas «desde», «por primera vez» ni «nunca antes» sin esa salvedad.")


@dataclass(frozen=True)
class CalendarPeriod:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def check_granularity(granularity: str) -> None:
    if granularity not in GRANULARITIES:
        raise ValueError("granularity tiene que ser day, week o month.")


def period_of(day: date, granularity: str) -> CalendarPeriod:
    """The calendar week (Monday to Sunday) or month that holds `day`."""
    if granularity == "week":
        start = day - timedelta(days=day.weekday())
        return CalendarPeriod(start, start + timedelta(days=6))
    if granularity == "month":
        start = day.replace(day=1)
        following = (start + timedelta(days=32)).replace(day=1)
        return CalendarPeriod(start, following - timedelta(days=1))
    return CalendarPeriod(day, day)


def periods_back(last_day: date, granularity: str, count: int) -> list[CalendarPeriod]:
    """The `count` periods that end with the one holding `last_day`, oldest first."""
    periods = [period_of(last_day, granularity)]
    while len(periods) < count:
        periods.insert(0, period_of(periods[0].start - timedelta(days=1), granularity))
    return periods


def periods_within(start: date, end: date, granularity: str) -> list[CalendarPeriod]:
    """The calendar periods that hold at least one day of [start, end], oldest first."""
    periods = [period_of(start, granularity)]
    while periods[-1].end < end:
        periods.append(period_of(periods[-1].end + timedelta(days=1), granularity))
    return periods


def coverage(period: CalendarPeriod, start: date, end: date) -> tuple[int, bool]:
    """(days_with_data, complete): how many of the period's days fall in [start, end], and whether all of them do."""
    first, last = max(period.start, start), min(period.end, end)
    covered = max(0, (last - first).days + 1)
    return covered, covered == period.days


def period_fields(period: CalendarPeriod, start: date, end: date) -> dict:
    covered, complete = coverage(period, start, end)
    return {"period_start": period.start.isoformat(), "period_end": period.end.isoformat(), "days": period.days,
            "days_with_data": covered, "complete": complete}


@dataclass(frozen=True)
class ActivityStart:
    first_day: date | None
    streak_start: date | None


def activity_start(values: list[tuple[date, float]]) -> ActivityStart:
    """The first day with a value above zero, and the first day of the unbroken run of them that reaches the last
    day; `values` is one per day, oldest first."""
    active = [day for day, value in values if value > 0]
    streak = None
    for day, value in reversed(values):
        if value <= 0:
            break
        streak = day
    return ActivityStart(active[0] if active else None, streak)


def activity_payload(read_from: date, values: dict[str, list[tuple[date, float]]]) -> dict:
    """When each figure's activity started and when its current run did, over the days read."""
    payload: dict = {"read_from": read_from.isoformat()}
    for figure, series in values.items():
        start = activity_start(series)
        payload[figure] = {"first_day": _iso(start.first_day), "streak_start": _iso(start.streak_start),
                           "reaches_read_start": start.first_day == read_from}
    return payload


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None

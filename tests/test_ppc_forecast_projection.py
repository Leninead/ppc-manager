"""The projection of PPC Forecast: a trend and a weekend difference fitted together, never counted twice.

Every expectation is derived by hand from series whose truth is known, so an error cannot hide behind a tolerance.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from core.ppc_forecast.projection import (
    DAY_TYPE,
    PROJECTED_SALES,
    WEEKDAY,
    WEEKEND,
    fit_sales_trend,
    forecast_sales,
    project_sales,
)


def _history(first: date, last: date, sales_on) -> pd.DataFrame:
    days = pd.date_range(first, last, freq="D")
    return pd.DataFrame({"_date": days, "_sales": [float(sales_on(day)) for day in days]})


def _repeated_week(day) -> float:
    return 60.0 if day.dayofweek >= 5 else 100.0


def _future_total(last: date, days: int, sales_on) -> float:
    return sum(sales_on(pd.Timestamp(last + timedelta(days=offset))) for offset in range(1, days + 1))


@pytest.mark.parametrize("last", [date(2026, 8, 28), date(2026, 8, 30)], ids=["ends-friday", "ends-sunday"])
@pytest.mark.parametrize("weeks", [2, 4, 8])
def test_a_history_that_repeats_one_week_projects_that_same_week_wherever_it_ends(weeks, last):
    history = _history(last - timedelta(days=7 * weeks - 1), last, _repeated_week)

    forecast = forecast_sales(history, 14, 0)

    assert forecast.projected_sales == pytest.approx(_future_total(last, 14, _repeated_week))
    assert forecast.trend.slope == pytest.approx(0.0, abs=1e-9)
    assert forecast.trend.weekend_ratio == pytest.approx(0.6)


def test_a_trend_with_a_weekend_difference_is_recovered_exactly():
    first = date(2026, 7, 6)

    def sales_on(day):
        return 200.0 + 3.0 * (day - pd.Timestamp(first)).days + (-50.0 if day.dayofweek >= 5 else 0.0)

    history = _history(first, date(2026, 8, 30), sales_on)

    trend = fit_sales_trend(history)

    assert (trend.intercept, trend.slope, trend.weekend_effect) == pytest.approx((200.0, 3.0, -50.0))
    assert forecast_sales(history, 30, 0).projected_sales == pytest.approx(_future_total(date(2026, 8, 30), 30,
                                                                                         sales_on))


def test_without_a_weekend_difference_the_projection_is_the_plain_line_the_module_always_drew():
    first = date(2026, 8, 1)
    history = _history(first, date(2026, 8, 30), lambda day: 150.0 + 2.5 * (day - pd.Timestamp(first)).days)
    slope, intercept = np.polyfit(np.arange(len(history), dtype=float), history["_sales"].to_numpy(), 1)

    forecast = forecast_sales(history, 14, 0)

    assert forecast.trend.weekend_ratio == pytest.approx(1.0)
    expected = [round(intercept + slope * (len(history) + offset), 2) for offset in range(14)]
    assert forecast.projection[PROJECTED_SALES].tolist() == pytest.approx(expected)


def test_the_weekend_ratio_compares_both_levels_in_the_middle_of_the_history():
    first = date(2026, 8, 3)
    history = _history(first, date(2026, 8, 30),
                       lambda day: 100.0 + 2.0 * (day - pd.Timestamp(first)).days + (30.0 if day.dayofweek >= 5 else 0))

    # The middle of 28 days is day 13.5, where a weekday sells 127.
    assert fit_sales_trend(history).weekend_ratio == pytest.approx(157.0 / 127.0)


def test_a_history_without_weekend_days_has_no_weekend_difference():
    weekdays = pd.bdate_range("2026-08-03", "2026-08-28")
    history = pd.DataFrame({"_date": weekdays, "_sales": [100.0] * len(weekdays)})

    forecast = forecast_sales(history, 7, 0)

    assert forecast.trend.weekend_effect is None and forecast.trend.weekend_ratio is None
    assert forecast.projection[PROJECTED_SALES].tolist() == pytest.approx([100.0] * 7)


def test_missing_days_count_as_calendar_days_in_the_trend():
    first = date(2026, 8, 3)
    history = _history(first, date(2026, 8, 30), lambda day: 10.0 + 1.0 * (day - pd.Timestamp(first)).days)
    history = history.drop(index=[5, 6, 12]).reset_index(drop=True)

    trend = fit_sales_trend(history)

    assert (trend.intercept, trend.slope) == pytest.approx((10.0, 1.0))


def test_a_falling_trend_never_projects_negative_sales():
    first = date(2026, 8, 3)
    history = _history(first, date(2026, 8, 16), lambda day: 100.0 - 8.0 * (day - pd.Timestamp(first)).days)

    projection = forecast_sales(history, 14, 0).projection

    assert projection[PROJECTED_SALES].min() == 0.0


def test_each_projected_day_says_whether_it_is_a_weekend_and_growth_applies_on_top():
    history = _history(date(2026, 8, 3), date(2026, 8, 30), _repeated_week)
    trend = fit_sales_trend(history)

    projection = project_sales(trend, pd.Timestamp("2026-08-30"), 7)
    forecast = forecast_sales(history, 14, 10)

    assert projection[DAY_TYPE].tolist() == [WEEKDAY] * 5 + [WEEKEND] * 2
    assert projection["Fecha"].tolist()[0] == "2026-08-31"
    assert forecast.horizon == 14
    assert forecast.sales_with_growth == pytest.approx(1240.0 * 1.10)
    assert forecast.average_daily_sales == pytest.approx((20 * 100.0 + 8 * 60.0) / 28)

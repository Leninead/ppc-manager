"""The daily sales projection of PPC Forecast: a straight trend and a weekend difference, fitted together.

Fitted together, the weekend is counted once. The former projection fitted the line over every day, so the line
already averaged weekdays and weekends, and then scaled the weekends of that line again by the weekend ratio; where
the history ended also tilted the line. A history repeating one week exactly (weekdays 100, weekends 60, four weeks
ending on a Sunday) was projected at 986.02 for the next 14 days instead of 1,240.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

WEEKEND_DAYS = (5, 6)
DATE = "Fecha"
WEEKDAY_NAME = "Día"
PROJECTED_SALES = "Ventas Proyectadas ($)"
DAY_TYPE = "Tipo"
WEEKEND = "Fin de semana"
WEEKDAY = "Laboral"


@dataclass(frozen=True)
class SalesTrend:
    """Sales on a day: intercept + slope × days since `first_date`, plus `weekend_effect` on Saturdays and Sundays."""

    first_date: pd.Timestamp
    intercept: float
    slope: float
    # None when the history has no weekday or no weekend day to compare.
    weekend_effect: float | None
    middle_day: float

    def sales_on(self, day: pd.Timestamp) -> float:
        on_weekend = self.weekend_effect is not None and day.dayofweek in WEEKEND_DAYS
        sales = self.intercept + self.slope * (day - self.first_date).days
        return max(sales + (self.weekend_effect if on_weekend else 0.0), 0.0)

    @property
    def weekend_ratio(self) -> float | None:
        """A Saturday's or Sunday's sales over a weekday's, in the middle of the history; None when unknown."""
        if self.weekend_effect is None:
            return None
        weekday = self.intercept + self.slope * self.middle_day
        return (weekday + self.weekend_effect) / weekday if weekday > 0 else None


@dataclass(frozen=True)
class SalesForecast:
    trend: SalesTrend
    projection: pd.DataFrame
    target_growth: int
    average_daily_sales: float

    @property
    def horizon(self) -> int:
        return len(self.projection)

    @property
    def projected_sales(self) -> float:
        return float(self.projection[PROJECTED_SALES].sum())

    @property
    def sales_with_growth(self) -> float:
        return self.projected_sales * (1 + self.target_growth / 100)


def fit_sales_trend(history: pd.DataFrame) -> SalesTrend:
    """Least squares over the history's `_date` and `_sales`, one row per day; gaps count as calendar days."""
    dates = history["_date"]
    first_date = dates.min()
    days = (dates - first_date).dt.days.to_numpy(dtype=float)
    on_weekend = dates.dt.dayofweek.isin(WEEKEND_DAYS).to_numpy()
    compares_weekends = bool(on_weekend.any() and not on_weekend.all())
    columns = [np.ones(len(days)), days] + ([on_weekend.astype(float)] if compares_weekends else [])
    coefficients = np.linalg.lstsq(np.column_stack(columns), history["_sales"].to_numpy(dtype=float), rcond=None)[0]
    return SalesTrend(first_date=first_date, intercept=float(coefficients[0]), slope=float(coefficients[1]),
                      weekend_effect=float(coefficients[2]) if compares_weekends else None,
                      middle_day=float(days.mean()))


def project_sales(trend: SalesTrend, last_date: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """One row per day after `last_date`: its date, weekday name, projected sales and whether it is a weekend."""
    rows = []
    for offset in range(1, horizon + 1):
        day = last_date + pd.Timedelta(days=offset)
        rows.append({DATE: day.strftime("%Y-%m-%d"), WEEKDAY_NAME: day.strftime("%A"),
                     PROJECTED_SALES: round(trend.sales_on(day), 2),
                     DAY_TYPE: WEEKEND if day.dayofweek in WEEKEND_DAYS else WEEKDAY})
    return pd.DataFrame(rows, columns=[DATE, WEEKDAY_NAME, PROJECTED_SALES, DAY_TYPE])


def forecast_sales(history: pd.DataFrame, horizon: int, target_growth: int) -> SalesForecast:
    trend = fit_sales_trend(history)
    return SalesForecast(trend=trend, projection=project_sales(trend, history["_date"].max(), horizon),
                         target_growth=target_growth, average_daily_sales=float(history["_sales"].mean()))

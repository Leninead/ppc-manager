"""The account's ads against the Business Report for this week and the prior one, each over its own days.

The weeks are the Business Report's: this week is its last seven days and the prior one the days before them. A week's
ACoS and TACoS add up the ads and the report over exactly the days both have, so each figure compares one period.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date

import pandas as pd

from core.amazon_ads.campaign_totals import ProductSeries
from core.business_report.paid_split import PaidSplit, paid_split


@dataclass(frozen=True)
class AdWeeks:
    """Each week's ads against the report; None for a week the account's campaign sync does not cover."""

    this_week: PaidSplit | None
    prior_week: PaidSplit | None


def ads_by_week(history: pd.DataFrame, ads: ProductSeries, this_week_start: date) -> AdWeeks:
    """`history` has one row per Business Report day (`_date`, `_sales`); `this_week_start` is its seventh-to-last day."""
    report_days = history["_date"].dt.date
    return AdWeeks(this_week=_week_split(history[report_days >= this_week_start], ads),
                   prior_week=_week_split(history[report_days < this_week_start], ads))


def _week_split(week: pd.DataFrame, ads: ProductSeries) -> PaidSplit | None:
    if week.empty:
        return None
    first, last = week["_date"].min().date(), week["_date"].max().date()
    days = tuple(day for day in ads.days if first <= day.day <= last)
    if not days:
        return None
    return paid_split(week, dataclasses.replace(ads, days=days))

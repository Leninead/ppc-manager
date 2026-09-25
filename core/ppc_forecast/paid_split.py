"""How much of the Business Report's sales came from ads, over the days the account's campaign reports also cover.

The ads side is the account's synced campaign reports (Sponsored Products, Brands and Display, counted as Campaign
Manager counts them): what the Campaign CSV the module used to ask for carried. Both sides sum the same days.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from core.amazon_ads.campaign_totals import ProductSeries


@dataclass(frozen=True)
class PaidSplit:
    """Ad spend and ad sales against the Business Report's sales of the same days."""

    start: date
    end: date
    covered_days: int
    history_days: int
    ad_spend: float
    ad_sales: float
    br_sales: float
    products: tuple[str, ...]
    currency_code: str
    attribution_days: int

    @property
    def acos(self) -> float | None:
        return self.ad_spend / self.ad_sales * 100 if self.ad_sales > 0 else None

    @property
    def tacos(self) -> float | None:
        return self.ad_spend / self.br_sales * 100 if self.br_sales > 0 else None

    @property
    def organic_sales(self) -> float:
        return max(self.br_sales - self.ad_sales, 0.0)

    @property
    def paid_share(self) -> float | None:
        return min(self.ad_sales / self.br_sales * 100, 100.0) if self.br_sales > 0 else None

    @property
    def ads_exceed_br(self) -> bool:
        """More ad sales than total sales on the same days: the account or country is likely not the report's."""
        return self.ad_sales > self.br_sales


def covered_window(first_day: date, last_day: date, synced_from: date | None,
                   synced_through: date | None) -> tuple[date, date] | None:
    """The Business Report's days that the campaign sync keeps, or None when they share none."""
    if synced_through is None:
        return None
    start = max(first_day, synced_from) if synced_from is not None else first_day
    end = min(last_day, synced_through)
    return (start, end) if start <= end else None


def paid_split(history: pd.DataFrame, ads: ProductSeries) -> PaidSplit:
    """The split over the days of `ads` that the Business Report (`_date`, `_sales`) also has."""
    start, end = ads.days[0].day, ads.days[-1].day
    report_days = history["_date"].dt.date
    covered = history[(report_days >= start) & (report_days <= end)]
    shared_days = set(covered["_date"].dt.date)
    ad_days = [day.totals for day in ads.days if day.day in shared_days]
    return PaidSplit(start=start, end=end, covered_days=len(shared_days), history_days=int(report_days.nunique()),
                     ad_spend=sum(totals.spend for totals in ad_days),
                     ad_sales=sum(totals.sales for totals in ad_days),
                     br_sales=float(covered["_sales"].sum()), products=ads.products,
                     currency_code=ads.currency_code, attribution_days=ads.attribution_days)


def spend_for_target(split: PaidSplit | None, target_sales: float) -> float | None:
    """The ad spend that keeps the covered days' TACoS at `target_sales`; None without ads figures."""
    if split is None or split.br_sales <= 0:
        return None
    return target_sales * split.ad_spend / split.br_sales

"""Each week's ads against the Business Report: ACoS and TACoS over exactly the days both have."""
from datetime import date, timedelta

import pandas as pd

from core.account_pulse.ads_by_week import ads_by_week
from core.amazon_ads.campaign_totals import ProductDay, ProductSeries, Totals

# Monday 3 to Sunday 16 August 2026: the prior week sells 100 a day, this week 150.
FIRST, LAST = date(2026, 8, 3), date(2026, 8, 16)
THIS_WEEK_START = date(2026, 8, 10)


def _history(first=FIRST, last=LAST) -> pd.DataFrame:
    days = pd.date_range(first, last, freq="D")
    return pd.DataFrame({"_date": days, "_sales": [150.0 if day.date() >= THIS_WEEK_START else 100.0 for day in days]})


def _ads(first=FIRST, last=LAST) -> ProductSeries:
    """Spends 10 a day; sells 40 a day in the prior week and 60 in this one."""
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    return ProductSeries(days=tuple(ProductDay(day, Totals(10.0, 60.0 if day >= THIS_WEEK_START else 40.0, 1, 5, 100,
                                                            0.0, 0)) for day in days),
                         campaigns=(), products=("SP",), currency_code="USD", attribution_days=7)


def test_each_week_compares_its_own_ads_with_its_own_sales():
    weeks = ads_by_week(_history(), _ads(), THIS_WEEK_START)

    this_week, prior_week = weeks.this_week, weeks.prior_week
    assert (this_week.start, this_week.end, this_week.covered_days, this_week.history_days) == (
        THIS_WEEK_START, LAST, 7, 7)
    # 70 of spend over 420 of ad sales and 1,050 of the report's sales.
    assert round(this_week.acos, 2) == 16.67 and round(this_week.tacos, 2) == 6.67
    # 70 of spend over 280 of ad sales and 700 of the report's sales.
    assert (prior_week.covered_days, round(prior_week.acos, 2), round(prior_week.tacos, 2)) == (7, 25.0, 10.0)


def test_a_week_the_sync_covers_in_part_sums_both_sides_over_those_days_only():
    weeks = ads_by_week(_history(), _ads(last=date(2026, 8, 14)), THIS_WEEK_START)

    this_week = weeks.this_week
    assert (this_week.covered_days, this_week.history_days) == (5, 7)
    # 50 of spend over the report's 750 of those five days, not over the whole week's 1,050.
    assert (this_week.ad_spend, this_week.br_sales) == (50.0, 750.0)


def test_a_week_the_sync_does_not_cover_has_no_figures():
    weeks = ads_by_week(_history(), _ads(first=THIS_WEEK_START), THIS_WEEK_START)

    assert weeks.prior_week is None
    assert weeks.this_week.covered_days == 7


def test_a_report_longer_than_two_weeks_counts_every_earlier_day_in_the_prior_week():
    history = _history(first=date(2026, 7, 27))

    weeks = ads_by_week(history, _ads(first=date(2026, 7, 27)), THIS_WEEK_START)

    assert (weeks.prior_week.covered_days, weeks.prior_week.history_days) == (14, 14)

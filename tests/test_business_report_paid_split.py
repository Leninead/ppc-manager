"""The split between ad sales and organic sales: the Business Report and the ads always sum the same days."""
from datetime import date, timedelta

import pandas as pd
import pytest

from core.amazon_ads.campaign_file import read_campaign_file
from core.amazon_ads.campaign_totals import ProductDay, ProductSeries, Totals
from core.business_report.paid_split import covered_window, file_split, paid_split, spend_for_target

FIRST, LAST = date(2026, 8, 3), date(2026, 8, 30)


def _history(first=FIRST, last=LAST, sales=100.0) -> pd.DataFrame:
    days = pd.date_range(first, last, freq="D")
    return pd.DataFrame({"_date": days, "_sales": [sales] * len(days)})


def _ads(first=FIRST, last=LAST, spend=10.0, sales=40.0, products=("SP", "SB")) -> ProductSeries:
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    return ProductSeries(days=tuple(ProductDay(day, Totals(spend, sales, 1, 5, 100, sales, 1)) for day in days),
                         campaigns=(), products=products, currency_code="USD", attribution_days=7)


@pytest.mark.parametrize("synced, expected", [
    ((date(2026, 7, 20), date(2026, 9, 22)), (FIRST, LAST)),
    ((date(2026, 8, 10), date(2026, 9, 22)), (date(2026, 8, 10), LAST)),
    ((date(2026, 6, 17), date(2026, 8, 20)), (FIRST, date(2026, 8, 20))),
    ((date(2026, 5, 28), date(2026, 7, 31)), None),
    ((None, None), None),
], ids=["covers-all", "starts-later", "ends-earlier", "no-shared-day", "never-synced"])
def test_the_covered_window_is_the_report_days_the_campaign_sync_keeps(synced, expected):
    assert covered_window(FIRST, LAST, *synced) == expected


def test_the_split_sums_ads_and_report_over_the_same_days():
    split = paid_split(_history(), _ads())

    assert (split.start, split.end, split.covered_days, split.history_days) == (FIRST, LAST, 28, 28)
    assert (split.ad_spend, split.ad_sales, split.br_sales) == pytest.approx((280.0, 1120.0, 2800.0))
    assert split.acos == pytest.approx(25.0)
    assert split.tacos == pytest.approx(10.0)
    assert split.organic_sales == pytest.approx(1680.0)
    assert split.paid_share == pytest.approx(40.0)
    assert split.products == ("SP", "SB") and split.currency_code == "USD" and split.attribution_days == 7
    assert not split.ads_exceed_br and not split.from_file


def test_a_day_missing_from_the_report_is_left_out_of_the_ads_too():
    history = _history().drop(index=[10]).reset_index(drop=True)

    split = paid_split(history, _ads())

    assert split.covered_days == 27 and split.history_days == 27
    assert (split.ad_spend, split.ad_sales, split.br_sales) == pytest.approx((270.0, 1080.0, 2700.0))


def test_only_the_covered_part_of_the_report_is_compared():
    split = paid_split(_history(), _ads(last=date(2026, 8, 20)))

    assert (split.covered_days, split.history_days) == (18, 28)
    assert split.br_sales == pytest.approx(1800.0)
    assert split.ad_spend == pytest.approx(180.0)


def test_more_ad_sales_than_report_sales_is_flagged_and_organic_stays_at_zero():
    split = paid_split(_history(sales=30.0), _ads())

    assert split.ads_exceed_br
    assert split.organic_sales == 0.0
    assert split.paid_share == 100.0


def test_without_sales_the_ratios_are_unknown_not_zero():
    split = paid_split(_history(sales=0.0), _ads(sales=0.0))

    assert split.acos is None and split.tacos is None and split.paid_share is None
    assert spend_for_target(split, 1000.0) is None


def test_the_spend_for_the_target_keeps_the_covered_days_tacos():
    split = paid_split(_history(), _ads())

    assert spend_for_target(split, 1500.0) == pytest.approx(150.0)
    assert spend_for_target(None, 1500.0) is None


def _campaign_file(spend="$320.00", sales="$1,280.00"):
    return read_campaign_file(("Campaign name,Type,Total cost,Sales\n"
                               f'Alpha,Sponsored Products,"{spend}","{sales}"\n'
                               "Beta,Sponsored Brands,$0.00,$0.00\n"
                               "Gamma,Sponsored Brands,$1.00,$0.00\n").encode("utf-8"), "campaigns.csv")


def test_a_campaign_csv_is_compared_with_the_whole_report_because_it_does_not_say_its_days():
    # Weekdays sell 100 and Saturdays and Sundays 60 over four whole weeks: 2,480.
    days = pd.date_range(FIRST, LAST, freq="D")
    history = pd.DataFrame({"_date": days, "_sales": [60.0 if day.dayofweek >= 5 else 100.0 for day in days]})

    split = file_split(history, _campaign_file(spend="$319.00"))

    assert (split.start, split.end, split.covered_days, split.history_days) == (FIRST, LAST, 28, 28)
    assert (split.ad_spend, split.ad_sales, split.br_sales) == pytest.approx((320.0, 1280.0, 2480.0))
    assert split.organic_sales == pytest.approx(1200.0)
    assert split.acos == pytest.approx(25.0)
    # 1,240 x 1.10 = 1,364 at a TACoS of 320 / 2,480: the estimate the module gave with the file.
    assert spend_for_target(split, 1364.0) == pytest.approx(176.0)
    assert split.from_file and split.attribution_days is None
    assert split.products == ("SP", "SB") and split.currency_code == ""


def test_a_campaign_csv_is_compared_with_the_days_the_report_has():
    history = _history().drop(index=[10]).reset_index(drop=True)

    split = file_split(history, _campaign_file())

    assert (split.covered_days, split.history_days) == (27, 27)
    assert split.br_sales == pytest.approx(2700.0)


def test_a_campaign_csv_that_sold_more_than_the_report_is_flagged():
    split = file_split(_history(sales=10.0), _campaign_file())

    assert split.ads_exceed_br and split.organic_sales == 0.0

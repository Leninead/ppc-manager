"""core/seller_reports/periods: the Search Query Performance periods, as the database validates them."""
from datetime import date, timedelta

from core.seller_reports.periods import MONTH, WEEK, SqpPeriod, sqp_month, sqp_week


def test_every_day_of_a_week_belongs_to_the_week_that_starts_on_its_sunday():
    sunday = date(2026, 9, 13)

    for offset in range(7):
        assert sqp_week(sunday + timedelta(days=offset)) == SqpPeriod(WEEK, sunday, date(2026, 9, 19))


def test_a_sunday_opens_a_new_week_and_a_saturday_closes_the_old_one():
    assert sqp_week(date(2026, 9, 20)).start == date(2026, 9, 20)
    assert sqp_week(date(2026, 9, 19)).end == date(2026, 9, 19)
    assert sqp_week(date(2026, 12, 31)) == SqpPeriod(WEEK, date(2026, 12, 27), date(2027, 1, 2))


def test_a_month_runs_from_its_first_day_to_its_last():
    assert sqp_month(date(2026, 9, 29)) == SqpPeriod(MONTH, date(2026, 9, 1), date(2026, 9, 30))
    assert sqp_month(date(2026, 2, 10)).end == date(2026, 2, 28)
    assert sqp_month(date(2028, 2, 1)).end == date(2028, 2, 29)
    assert sqp_month(date(2026, 12, 31)) == SqpPeriod(MONTH, date(2026, 12, 1), date(2026, 12, 31))

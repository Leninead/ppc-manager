"""search_term_rows: report file loading and mapping to ads_search_term_daily rows. Synthetic rows only."""
from __future__ import annotations

import gzip
import json
from datetime import date

import pytest

from core.amazon_ads import search_term_rows
from core.amazon_ads.search_term_rows import (
    ReportRowsError,
    compact_rows,
    day_row_positions,
    day_rows,
    load_compact_report,
    load_report,
    rows_by_day,
)

WINDOW_START = date(2026, 9, 1)
WINDOW_END = date(2026, 9, 3)


def _api_row(**overrides) -> dict:
    row = {
        "date": "2026-09-02",
        "campaignId": 158410630682987,
        "campaignName": "Demo - SP - KW - EXACT",
        "campaignStatus": "ENABLED",
        "adGroupId": 290001112223334,
        "adGroupName": "Demo ad group",
        "keywordId": 401234567890123,
        "keyword": "demo keyword",
        "keywordType": "EXACT",
        "matchType": "EXACT",
        "targeting": "demo keyword",
        "adKeywordStatus": "ENABLED",
        "portfolioId": 77788899900011,
        "searchTerm": "demo search term",
        "campaignBudgetCurrencyCode": "MXN",
        "impressions": 120,
        "clicks": 4,
        "cost": 3.25,
        "purchases7d": 1,
        "sales7d": 19.99,
        "unitsSoldClicks7d": 1,
        "purchases14d": 2,
        "sales14d": 39.98,
        "unitsSoldClicks14d": 2,
    }
    row.update(overrides)
    return row


def _rows(api_rows, **kwargs):
    arguments = {"profile_id": "555", "currency_code": "MXN", "window_start": WINDOW_START,
                 "window_end": WINDOW_END}
    arguments.update(kwargs)
    return rows_by_day(api_rows, **arguments)


def test_maps_api_fields_to_table_columns():
    by_day = _rows([_api_row()])

    assert by_day[date(2026, 9, 2)] == [{
        "profile_id": "555",
        "report_date": "2026-09-02",
        "campaign_id": "158410630682987",
        "campaign_name": "Demo - SP - KW - EXACT",
        "campaign_status": "ENABLED",
        "ad_group_id": "290001112223334",
        "ad_group_name": "Demo ad group",
        "keyword_type": "EXACT",
        "keyword_id": "401234567890123",
        "keyword_text": "demo keyword",
        "match_type": "EXACT",
        "targeting": "demo keyword",
        "ad_keyword_status": "ENABLED",
        "portfolio_id": "77788899900011",
        "search_term": "demo search term",
        "impressions": 120,
        "clicks": 4,
        "cost": 3.25,
        "purchases_7d": 1,
        "sales_7d": 19.99,
        "units_7d": 1,
        "purchases_14d": 2,
        "sales_14d": 39.98,
        "units_14d": 2,
        "currency_code": "MXN",
    }]


def test_rows_serialize_to_json_for_the_day_replace_rpc():
    by_day = _rows([_api_row()])

    json.dumps(by_day[date(2026, 9, 2)])


def test_every_window_day_is_present_even_without_rows():
    by_day = _rows([_api_row(date="2026-09-02")])

    assert list(by_day) == [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    assert by_day[date(2026, 9, 1)] == []
    assert by_day[date(2026, 9, 3)] == []


def test_empty_report_still_lists_every_day():
    by_day = _rows([])

    assert by_day == {date(2026, 9, 1): [], date(2026, 9, 2): [], date(2026, 9, 3): []}


def test_ids_are_exact_text_not_float_renderings():
    by_day = _rows([_api_row(campaignId=1.58410630682987e14, adGroupId="290001112223334 ", keywordId=None,
                             portfolioId=None)])

    row = by_day[date(2026, 9, 2)][0]
    assert row["campaign_id"] == "158410630682987"
    assert row["ad_group_id"] == "290001112223334"
    assert row["keyword_id"] == ""
    assert row["portfolio_id"] == ""


def test_missing_values_become_empty_text_and_zero_metrics():
    by_day = _rows([_api_row(keyword=None, targeting=None, adKeywordStatus=None, sales14d=None,
                             purchases14d=None, unitsSoldClicks14d=None, impressions=None)])

    row = by_day[date(2026, 9, 2)][0]
    assert row["keyword_text"] == ""
    assert row["targeting"] == ""
    assert row["ad_keyword_status"] == ""
    assert row["sales_14d"] == 0
    assert row["purchases_14d"] == 0
    assert row["units_14d"] == 0
    assert row["impressions"] == 0


def test_seven_and_fourteen_day_attribution_are_kept_apart():
    row = _rows([_api_row(purchases7d=1, sales7d=10.0, unitsSoldClicks7d=1,
                          purchases14d=3, sales14d=30.0, unitsSoldClicks14d=4)])[date(2026, 9, 2)][0]

    assert (row["purchases_7d"], row["sales_7d"], row["units_7d"]) == (1, 10.0, 1)
    assert (row["purchases_14d"], row["sales_14d"], row["units_14d"]) == (3, 30.0, 4)


def test_duplicate_primary_key_rows_are_summed():
    first = _api_row(impressions=100, clicks=2, cost=0.1, sales7d=5.0, purchases7d=1, unitsSoldClicks7d=1)
    second = _api_row(impressions=50, clicks=1, cost=0.2, sales7d=7.5, purchases7d=2, unitsSoldClicks7d=3)

    rows = _rows([first, second])[date(2026, 9, 2)]

    assert len(rows) == 1
    assert rows[0]["impressions"] == 150
    assert rows[0]["clicks"] == 3
    assert rows[0]["cost"] == 0.3
    assert rows[0]["sales_7d"] == 12.5
    assert rows[0]["purchases_7d"] == 3
    assert rows[0]["units_7d"] == 4


@pytest.mark.parametrize("field, value", [
    ("keywordType", "PHRASE"),
    ("matchType", "BROAD"),
    ("keywordId", 999),
    ("targeting", "other target"),
    ("searchTerm", "Demo Search Term"),
    ("adGroupId", 1),
    ("campaignId", 2),
])
def test_rows_differing_in_any_key_column_stay_separate(field, value):
    rows = _rows([_api_row(), _api_row(**{field: value})])[date(2026, 9, 2)]

    assert len(rows) == 2


def test_same_key_on_different_days_is_not_merged():
    by_day = _rows([_api_row(date="2026-09-01"), _api_row(date="2026-09-03")])

    assert len(by_day[date(2026, 9, 1)]) == 1
    assert len(by_day[date(2026, 9, 3)]) == 1


def test_row_currency_falls_back_to_profile_currency():
    row = _rows([_api_row(campaignBudgetCurrencyCode=None)], currency_code="usd")[date(2026, 9, 2)][0]

    assert row["currency_code"] == "USD"


@pytest.mark.parametrize("bad_date", ["2026-08-31", "2026-09-04"])
def test_row_outside_the_window_is_rejected(bad_date):
    with pytest.raises(ReportRowsError, match="outside"):
        _rows([_api_row(date=bad_date)])


@pytest.mark.parametrize("bad_date", [None, "", "yesterday"])
def test_row_without_a_valid_date_is_rejected(bad_date):
    with pytest.raises(ReportRowsError):
        _rows([_api_row(date=bad_date)])


_COLUMN_OF = {"sales7d": "sales_7d", "purchases14d": "purchases_14d", "unitsSoldClicks7d": "units_7d"}


@pytest.mark.parametrize("field", ["impressions", "clicks", "cost", "sales7d", "purchases14d", "unitsSoldClicks7d"])
def test_a_metric_below_zero_is_stored_as_zero_instead_of_failing_the_report(field, caplog):
    # Amazon nets invalid traffic out of days it already reported; below zero the day simply had none.
    with caplog.at_level("WARNING", logger="core.amazon_ads.search_term_rows"):
        (row,) = _rows([_api_row(**{field: -1})])[date(2026, 9, 2)]

    assert row[_COLUMN_OF.get(field, field)] == 0
    assert "1 values below zero" in caplog.text and f"{field}=-1" in caplog.text


def test_a_metric_that_is_not_a_finite_number_is_rejected():
    for value in (float("nan"), float("inf")):
        with pytest.raises(ReportRowsError, match="impossible"):
            _rows([_api_row(cost=value)])


def test_non_numeric_metric_is_rejected():
    with pytest.raises(ReportRowsError, match="non-numeric"):
        _rows([_api_row(clicks="many")])


def test_window_ending_before_start_is_rejected():
    with pytest.raises(ReportRowsError):
        _rows([], window_start=date(2026, 9, 3), window_end=date(2026, 9, 1))


def test_day_positions_group_rows_by_day_and_one_day_is_built_at_a_time():
    api_rows = [_api_row(date="2026-09-03"), _api_row(date="2026-09-01", clicks=1),
                _api_row(date="2026-09-03", clicks=6)]
    report_rows = compact_rows(api_rows)

    positions_by_day = day_row_positions(report_rows, window_start=WINDOW_START, window_end=WINDOW_END)

    assert positions_by_day == {date(2026, 9, 1): [1], date(2026, 9, 2): [], date(2026, 9, 3): [0, 2]}
    rows = day_rows(report_rows, positions_by_day[date(2026, 9, 3)], profile_id="555", currency_code="MXN",
                    day=date(2026, 9, 3))
    assert rows == _rows(api_rows)[date(2026, 9, 3)]
    assert len(rows) == 1 and rows[0]["clicks"] == 10


@pytest.mark.parametrize("bad_row", [_api_row(date="2026-09-03", cost=float("nan")), _api_row(date="2026-09-04"),
                                     "not a row"])
def test_one_unusable_row_on_a_later_day_refuses_the_whole_report(bad_row):
    with pytest.raises(ReportRowsError):
        day_row_positions(compact_rows([_api_row(date="2026-09-01"), bad_row]), window_start=WINDOW_START,
                          window_end=WINDOW_END)


def test_compact_report_holds_only_the_fields_the_table_needs(tmp_path):
    report_path = tmp_path / "report.json.gz"
    with gzip.open(report_path, "wt", encoding="utf-8") as report_file:
        json.dump([_api_row(unusedMetric=7, extraText="x" * 50)], report_file)

    report_rows = load_compact_report(report_path)

    assert len(report_rows) == 1 and "x" * 50 not in report_rows[0] and 7 not in report_rows[0]
    assert day_rows(report_rows, [0], profile_id="555", currency_code="MXN", day=date(2026, 9, 2)) == \
        _rows([_api_row()])[date(2026, 9, 2)]


def test_report_is_read_across_chunk_boundaries_without_losing_or_splitting_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(search_term_rows, "_READ_CHARS", 7)
    api_rows = [123456789, _api_row(impressions=123456789, searchTerm='quote " and ], { inside'),
                _api_row(cost=0.000125)]
    report_path = tmp_path / "report.json.gz"
    with gzip.open(report_path, "wt", encoding="utf-8") as report_file:
        report_file.write("  [\n" + ",\n ".join(json.dumps(row) for row in api_rows) + "\n]\n")

    assert load_report(report_path) == api_rows


@pytest.mark.parametrize("content", ["[", '[{"date": "2026-09-02"}', '[{"date": "2026-09-02"},]', "[1 2]",
                                     '[{"date": "2026-09-02"}] trailing', ""])
def test_truncated_or_malformed_arrays_are_rejected(tmp_path, content):
    report_path = tmp_path / "report.json.gz"
    report_path.write_text(content, encoding="utf-8")

    with pytest.raises(ReportRowsError):
        load_report(report_path)


def test_an_empty_array_is_an_empty_report(tmp_path):
    report_path = tmp_path / "report.json.gz"
    report_path.write_text(" [ ] ", encoding="utf-8")

    assert load_report(report_path) == []


def test_load_report_reads_gzip_json(tmp_path):
    report_path = tmp_path / "report.json.gz"
    with gzip.open(report_path, "wt", encoding="utf-8") as report_file:
        json.dump([_api_row()], report_file)

    assert load_report(report_path) == [_api_row()]


def test_load_report_tolerates_an_already_decompressed_file(tmp_path):
    report_path = tmp_path / "report.json.gz"
    report_path.write_text(json.dumps([_api_row()]), encoding="utf-8")

    assert load_report(report_path) == [_api_row()]


@pytest.mark.parametrize("content", [b"\x1f\x8bnot really gzip", b"{not json", b'{"rows": []}'])
def test_load_report_rejects_unusable_files(tmp_path, content):
    report_path = tmp_path / "report.json.gz"
    report_path.write_bytes(content)

    with pytest.raises(ReportRowsError):
        load_report(report_path)

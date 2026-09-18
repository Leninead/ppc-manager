"""spCampaigns report rows mapped to `ads_campaign_daily`, grouped by report day.

Only the metrics live here. A campaign's name, state, budget and start date come from
`campaign_entities`, because the report carries no row at all for a campaign that had no
activity — and its `startDate` is the edge of the range asked for, not the campaign's own.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from core.amazon_ads.report_fetcher import ReportSpec
from core.amazon_ads.search_term_rows import ReportRowsError, iter_report

MONEY_DECIMALS = 4

_COUNT_COLUMNS = {
    "impressions": "impressions",
    "clicks": "clicks",
    "purchases_7d": "purchases7d",
    "purchases_14d": "purchases14d",
}
_MONEY_COLUMNS = {
    "cost": "cost",
    "sales_7d": "sales7d",
    "sales_14d": "sales14d",
}
_CURRENCY_FIELD = "campaignBudgetCurrencyCode"
_SOURCE_FIELDS = ("date", "campaignId", *_COUNT_COLUMNS.values(), *_MONEY_COLUMNS.values(), _CURRENCY_FIELD)
_FIELD_INDEX = {field: index for index, field in enumerate(_SOURCE_FIELDS)}
_METRIC_FIELDS = (*_COUNT_COLUMNS.values(), *_MONEY_COLUMNS.values())

# Asking for exactly the fields this module reads is what keeps request and mapping from drifting.
CAMPAIGN_REPORT_SPEC = ReportSpec(
    report_type_id="spCampaigns",
    group_by=("campaign",),
    columns=_SOURCE_FIELDS,
)


def load_compact_report(gzip_path) -> list[tuple]:
    """The report's rows as compact rows, which take far less memory than its parsed JSON objects."""
    return compact_rows(iter_report(gzip_path))


def compact_rows(api_rows: Iterable) -> list[tuple]:
    compacted = []
    for position, api_row in enumerate(api_rows):
        if not isinstance(api_row, dict):
            raise ReportRowsError(f"campaign report row {position} is not an object")
        compacted.append(tuple(api_row.get(field) for field in _SOURCE_FIELDS))
    return compacted


def rows_by_day(
    api_rows: Iterable[dict],
    *,
    profile_id: str,
    currency_code: str,
    window_start: date,
    window_end: date,
) -> dict[date, list[dict]]:
    """Every day of the window as a key (empty list when the report had nothing that day);
    rows sharing a campaign are merged by summing their metrics."""
    report_rows = compact_rows(api_rows)
    positions_by_day = day_row_positions(report_rows, window_start=window_start, window_end=window_end)
    return {
        day: day_rows(report_rows, positions, profile_id=profile_id, currency_code=currency_code, day=day)
        for day, positions in positions_by_day.items()
    }


def day_row_positions(report_rows: Sequence[tuple], *, window_start: date,
                      window_end: date) -> dict[date, list[int]]:
    """Every day of the window as a key, with the positions of that day's rows.

    Checks every row, so a report with one unusable row is refused before any day is written.
    """
    if window_end < window_start:
        raise ReportRowsError(f"window ends before it starts: {window_start}..{window_end}")
    positions_by_day: dict[date, list[int]] = {
        window_start + timedelta(days=offset): []
        for offset in range((window_end - window_start).days + 1)
    }
    for position, report_row in enumerate(report_rows):
        report_day = _report_day(report_row, position)
        if report_day not in positions_by_day:
            raise ReportRowsError(
                f"campaign report row {position} is dated {report_day}, outside {window_start}..{window_end}"
            )
        if not _id_text(report_row[_FIELD_INDEX["campaignId"]]):
            raise ReportRowsError(f"campaign report row {position} has no campaign id")
        for field in _METRIC_FIELDS:
            _metric(report_row[_FIELD_INDEX[field]], field, position)
        positions_by_day[report_day].append(position)
    return positions_by_day


def day_rows(report_rows: Sequence[tuple], positions: Iterable[int], *, profile_id: str,
             currency_code: str, day: date) -> list[dict]:
    """One day's table rows from rows checked by `day_row_positions`; repeated campaigns are summed."""
    merged: dict[str, dict] = {}
    for position in positions:
        row = _table_row(report_rows[position], position, profile_id, currency_code, day)
        existing = merged.get(row["campaign_id"])
        if existing is None:
            merged[row["campaign_id"]] = row
        else:
            _add_metrics(existing, row)
    return list(merged.values())


def _table_row(report_row: tuple, position: int, profile_id: str, currency_code: str,
               report_day: date) -> dict:
    row: dict = {
        "profile_id": profile_id,
        "report_date": report_day.isoformat(),
        "campaign_id": _id_text(report_row[_FIELD_INDEX["campaignId"]]),
    }
    for column, field in _COUNT_COLUMNS.items():
        row[column] = int(round(_metric(report_row[_FIELD_INDEX[field]], field, position)))
    for column, field in _MONEY_COLUMNS.items():
        row[column] = round(_metric(report_row[_FIELD_INDEX[field]], field, position), MONEY_DECIMALS)
    row["currency_code"] = str(report_row[_FIELD_INDEX[_CURRENCY_FIELD]] or currency_code or "").strip().upper()
    return row


def _add_metrics(existing: dict, duplicate: dict) -> None:
    for column in _COUNT_COLUMNS:
        existing[column] += duplicate[column]
    for column in _MONEY_COLUMNS:
        existing[column] = round(existing[column] + duplicate[column], MONEY_DECIMALS)


def _report_day(report_row: tuple, position: int) -> date:
    raw_date = str(report_row[_FIELD_INDEX["date"]] or "").strip()
    try:
        return date.fromisoformat(raw_date[:10])
    except ValueError:
        raise ReportRowsError(f"campaign report row {position} has no valid date") from None


def _id_text(value) -> str:
    # Amazon sends ids as JSON numbers; a float rendering ("1.5e+14") would break every join.
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _metric(value, field: str, position: int) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise ReportRowsError(f"campaign report row {position} has a non-numeric {field}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ReportRowsError(f"campaign report row {position} has a non-numeric {field}") from None
    if not math.isfinite(number) or number < 0:
        raise ReportRowsError(f"campaign report row {position} has an impossible {field}: {number}")
    return number

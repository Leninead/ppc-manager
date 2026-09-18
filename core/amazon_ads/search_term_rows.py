"""spSearchTerm report rows mapped to `ads_search_term_daily`, grouped by report day.

A saved report is read as compact rows (the fields the table needs, in `_SOURCE_FIELDS` order) and
turned into table rows one day at a time, so a large report never sits in memory as parsed JSON objects.
"""
from __future__ import annotations

import gzip
import json
import logging
import math
import re
import zlib
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import TextIO

log = logging.getLogger(__name__)

GZIP_MAGIC = b"\x1f\x8b"
MONEY_DECIMALS = 4

_TEXT_COLUMNS = {
    "campaign_name": "campaignName",
    "campaign_status": "campaignStatus",
    "ad_group_name": "adGroupName",
    "keyword_type": "keywordType",
    "keyword_text": "keyword",
    "match_type": "matchType",
    "targeting": "targeting",
    "ad_keyword_status": "adKeywordStatus",
    "search_term": "searchTerm",
}
_ID_COLUMNS = {
    "campaign_id": "campaignId",
    "ad_group_id": "adGroupId",
    "keyword_id": "keywordId",
    "portfolio_id": "portfolioId",
}
_COUNT_COLUMNS = {
    "impressions": "impressions",
    "clicks": "clicks",
    "purchases_7d": "purchases7d",
    "units_7d": "unitsSoldClicks7d",
    "purchases_14d": "purchases14d",
    "units_14d": "unitsSoldClicks14d",
}
_MONEY_COLUMNS = {
    "cost": "cost",
    "sales_7d": "sales7d",
    "sales_14d": "sales14d",
}
_KEY_COLUMNS = ("campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting", "search_term")
_CURRENCY_FIELD = "campaignBudgetCurrencyCode"
_SOURCE_FIELDS = ("date", *_ID_COLUMNS.values(), *_TEXT_COLUMNS.values(), *_COUNT_COLUMNS.values(),
                  *_MONEY_COLUMNS.values(), _CURRENCY_FIELD)
_FIELD_INDEX = {field: index for index, field in enumerate(_SOURCE_FIELDS)}
_METRIC_FIELDS = (*_COUNT_COLUMNS.values(), *_MONEY_COLUMNS.values())
_READ_CHARS = 1 << 20
_JSON_WHITESPACE = re.compile(r"[ \t\n\r]*")


class ReportRowsError(ValueError):
    """The report file cannot be trusted: unreadable, out of window, or impossible values."""


def load_report(gzip_path: Path) -> list[dict]:
    return list(iter_report(gzip_path))


def load_compact_report(gzip_path: Path) -> list[tuple]:
    """The report's rows as compact rows, which take far less memory than its parsed JSON objects."""
    return compact_rows(iter_report(gzip_path))


def iter_report(gzip_path: Path) -> Iterator:
    """The items of the report's JSON array, parsed one at a time so the file's text is never held whole."""
    name = Path(gzip_path).name
    try:
        with open(gzip_path, "rb") as probe:
            is_gzip = probe.read(2) == GZIP_MAGIC
        opener = gzip.open if is_gzip else open
        with opener(gzip_path, "rt", encoding="utf-8") as report_file:
            yield from _json_array_items(report_file, name)
    except (OSError, EOFError, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportRowsError(f"unreadable report file {name}: {type(exc).__name__}") from exc


def compact_rows(api_rows: Iterable) -> list[tuple]:
    compacted = []
    for position, api_row in enumerate(api_rows):
        if not isinstance(api_row, dict):
            raise ReportRowsError(f"report row {position} is not an object")
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
    """Every day of the window as a key (empty list when Amazon had no clicks that day);
    rows sharing the table's primary key are merged by summing their metrics."""
    report_rows = compact_rows(api_rows)
    positions_by_day = day_row_positions(report_rows, window_start=window_start, window_end=window_end)
    return {
        day: day_rows(report_rows, positions, profile_id=profile_id, currency_code=currency_code, day=day)
        for day, positions in positions_by_day.items()
    }


def day_row_positions(report_rows: Sequence[tuple], *, window_start: date,
                      window_end: date) -> dict[date, list[int]]:
    """Every day of the window as a key, with the positions of that day's compact rows.

    Checks every row, so a report with one unusable row is refused before any day is written.
    """
    if window_end < window_start:
        raise ReportRowsError(f"window ends before it starts: {window_start}..{window_end}")
    positions_by_day: dict[date, list[int]] = {
        window_start + timedelta(days=offset): []
        for offset in range((window_end - window_start).days + 1)
    }
    negatives: list[tuple] = []
    for position, report_row in enumerate(report_rows):
        report_day = _report_day(report_row, position)
        if report_day not in positions_by_day:
            raise ReportRowsError(
                f"report row {position} is dated {report_day}, outside {window_start}..{window_end}"
            )
        for field in _METRIC_FIELDS:
            number = _number(report_row[_FIELD_INDEX[field]], field, position)
            if number < 0:
                negatives.append((report_day, _id_text(report_row[_FIELD_INDEX["campaignId"]]), field, number))
        positions_by_day[report_day].append(position)
    if negatives:
        day, campaign_id, field, number = negatives[0]
        log.warning("amazon_ads: search term report %s..%s has %d values below zero (Amazon adjustments), stored"
                    " as 0; first: campaign %s on %s %s=%s", window_start, window_end, len(negatives), campaign_id,
                    day, field, number)
    return positions_by_day


def day_rows(report_rows: Sequence[tuple], positions: Iterable[int], *, profile_id: str, currency_code: str,
             day: date) -> list[dict]:
    """One day's table rows from rows checked by `day_row_positions`; rows sharing a primary key are summed."""
    merged: dict[tuple, dict] = {}
    for position in positions:
        row = _table_row(report_rows[position], position, profile_id, currency_code, day)
        key = tuple(row[column] for column in _KEY_COLUMNS)
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
        else:
            _add_metrics(existing, row)
    return list(merged.values())


def _json_array_items(report_file: TextIO, name: str) -> Iterator:
    decoder = json.JSONDecoder()
    buffer, position, exhausted = "", 0, False
    expected = "["
    while True:
        position = _JSON_WHITESPACE.match(buffer, position).end()
        if position == len(buffer):
            if exhausted:
                raise ReportRowsError(f"report file {name} is not a JSON array" if expected == "["
                                      else f"report file {name} ends before its JSON array closes")
            buffer, position, exhausted = _read_more(report_file, buffer, position)
            continue
        character = buffer[position]
        if expected == "[":
            if character != "[":
                raise ReportRowsError(f"report file {name} is not a JSON array")
            position, expected = position + 1, "first item"
        elif character == "]" and expected in ("first item", "separator"):
            if (buffer[position + 1:] + report_file.read()).strip():
                raise ReportRowsError(f"report file {name} has data after its JSON array")
            return
        elif character == "," and expected == "separator":
            position, expected = position + 1, "item"
        elif expected in ("first item", "item"):
            try:
                item, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                if exhausted:
                    raise
                buffer, position, exhausted = _read_more(report_file, buffer, position)
                continue
            # A number or literal that touches the end of the buffer may continue in the next chunk.
            if end == len(buffer) and not exhausted:
                buffer, position, exhausted = _read_more(report_file, buffer, position)
                continue
            yield item
            position, expected = end, "separator"
        else:
            raise ReportRowsError(f"report file {name} is not a valid JSON array")


def _read_more(report_file: TextIO, buffer: str, position: int) -> tuple[str, int, bool]:
    chunk = report_file.read(_READ_CHARS)
    return buffer[position:] + chunk, 0, not chunk


def _table_row(report_row: tuple, position: int, profile_id: str, currency_code: str, report_day: date) -> dict:
    row: dict = {"profile_id": profile_id, "report_date": report_day.isoformat()}
    for column, field in _ID_COLUMNS.items():
        row[column] = _id_text(report_row[_FIELD_INDEX[field]])
    for column, field in _TEXT_COLUMNS.items():
        value = report_row[_FIELD_INDEX[field]]
        row[column] = "" if value is None else str(value)
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
        raise ReportRowsError(f"report row {position} has no valid date") from None


def _id_text(value) -> str:
    # Amazon sends ids as JSON numbers; a float rendering ("1.5e+14") would break joins with the bulk file.
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value, field: str, position: int) -> float:
    """The value as a finite number, sign kept; a report with one that is not a number cannot be trusted."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise ReportRowsError(f"report row {position} has a non-numeric {field}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ReportRowsError(f"report row {position} has a non-numeric {field}") from None
    if not math.isfinite(number):
        raise ReportRowsError(f"report row {position} has an impossible {field}: {number}")
    return number


def _metric(value, field: str, position: int) -> float:
    # Amazon removes invalid traffic from days it already reported, and on a day with nothing else the net can fall
    # below zero (seen in the campaign report: impressions -2 on a day with no activity). Every reader sums these as
    # counts that are never negative, so the day keeps none; `day_row_positions` logs what was adjusted.
    return max(_number(value, field, position), 0.0)

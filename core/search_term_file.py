"""Reads a manually uploaded Search Term report into canonical sources, one per advertiser account.

Legacy console files pass through untouched; the 2026 console csv is mapped to the canonical frame.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import pandas as pd

from core import search_term_frame as canonical
from core.search_term_frame import SOURCE_FILE, SearchTermSource, add_ratios, valid_currency_code

log = logging.getLogger(__name__)

FORMAT_CONSOLE_LEGACY = "console_legacy"
FORMAT_CONSOLE_2026 = "console_2026"
FORMAT_UNKNOWN = "unknown"

ALL_ACCOUNTS_KEY = "all"
UNIDENTIFIED_ACCOUNT_KEY = "unidentified"
DEFAULT_ATTRIBUTION_DAYS = 7
# The 2026 export does not state its attribution window; seller Sponsored Products metrics default to 7 days.
CONSOLE_2026_ATTRIBUTION_DAYS = 7

_LEGACY_REQUIRED_HEADERS = ("customer search term", "spend")
_CONSOLE_2026_REQUIRED_HEADERS = ("search term", "total cost", "sales", "purchases")
_ATTRIBUTION_HEADER = re.compile(r"^(\d+) day total sales")

_CONSOLE_2026_TEXT_COLUMNS = {
    canonical.SEARCH_TERM: "search term",
    canonical.CAMPAIGN_NAME: "campaign name",
    canonical.AD_GROUP_NAME: "ad group name",
    canonical.PORTFOLIO_NAME: "portfolio name",
    "_campaign_id": "campaign id",
    "_ad_group_id": "ad group id",
}
_CONSOLE_2026_COUNT_COLUMNS = {
    canonical.IMPRESSIONS: "impressions",
    canonical.CLICKS: "clicks",
    canonical.orders_column(CONSOLE_2026_ATTRIBUTION_DAYS): "purchases",
    canonical.units_column(CONSOLE_2026_ATTRIBUTION_DAYS): "units sold",
}
_CONSOLE_2026_AMOUNT_COLUMNS = {
    canonical.SPEND: "total cost",
    canonical.sales_column(CONSOLE_2026_ATTRIBUTION_DAYS): "sales",
}


class SearchTermFileError(ValueError):
    """The uploaded bytes could not be read as a table; the message is shown to the user."""


@dataclass(frozen=True)
class FileAccount:
    key: str
    name: str
    currency_code: str
    row_count: int


@dataclass(frozen=True, eq=False)
class SearchTermFile:
    format: str
    accounts: tuple[FileAccount, ...]
    attribution_days: int
    account_frames: Mapping[str, pd.DataFrame] = field(repr=False)

    def source_for(self, account_key: str, *, file_name: str, file_bytes_digest: str) -> SearchTermSource:
        account = next((account for account in self.accounts if account.key == account_key), None)
        if account is None:
            raise KeyError(f"Account {account_key!r} is not in {file_name!r}; "
                           f"available: {[account.key for account in self.accounts]}")
        label = file_name if account.key == ALL_ACCOUNTS_KEY else f"{account.name} · {file_name}"
        return SearchTermSource(
            # A copy, so the page's in-place column additions never leak into the next rerun.
            frame=self.account_frames[account_key].copy(),
            source=SOURCE_FILE,
            currency_code=account.currency_code,
            label=label,
            signature=f"{file_bytes_digest[:16]}:{account_key}",
            attribution_days=self.attribution_days,
            bulk_ready=False,
        )


def read_search_term_file(file_bytes: bytes, file_name: str) -> SearchTermFile:
    headers = _read_table(file_bytes, file_name, header_only=True).columns
    file_format = _detect_format(headers)
    table = _read_table(file_bytes, file_name, as_text=file_format == FORMAT_CONSOLE_2026)

    if file_format == FORMAT_CONSOLE_2026:
        search_term_file = _read_console_2026(table, file_name)
    elif file_format == FORMAT_CONSOLE_LEGACY:
        search_term_file = _read_console_legacy(table, file_name)
    else:
        search_term_file = _single_account_file(FORMAT_UNKNOWN, table, file_name, currency_code="",
                                                attribution_days=DEFAULT_ATTRIBUTION_DAYS)
    log.info("Search term file %r read as %s: %d rows, %d accounts", file_name, file_format,
             len(table), len(search_term_file.accounts))
    return search_term_file


def _read_table(file_bytes: bytes, file_name: str, *, as_text: bool = False,
                header_only: bool = False) -> pd.DataFrame:
    options: dict = {}
    if header_only:
        options["nrows"] = 0
    if as_text:
        # Ids longer than 15 digits lose precision once pandas parses them as floats.
        options.update(dtype=str, keep_default_na=False)
    buffer = io.BytesIO(file_bytes)
    try:
        if file_name.lower().endswith(".xlsx"):
            return pd.read_excel(buffer, **options)
        return pd.read_csv(buffer, encoding="utf-8-sig", **options)
    except (ValueError, zipfile.BadZipFile, OSError) as exc:
        log.warning("Search term file %r could not be read: %s: %s", file_name, type(exc).__name__, exc)
        raise SearchTermFileError(
            f"No se pudo leer «{file_name}». Revisá que sea el .xlsx o .csv exportado de Amazon Ads."
        ) from exc


def _normalized_header(column: object) -> str:
    return str(column).replace("\N{ZERO WIDTH NO-BREAK SPACE}", "").strip().casefold()


def _columns_by_header(columns: Iterable) -> dict[str, object]:
    by_header: dict[str, object] = {}
    for column in columns:
        by_header.setdefault(_normalized_header(column), column)
    return by_header


def _detect_format(columns: Iterable) -> str:
    headers = set(_columns_by_header(columns))
    if all(header in headers for header in _CONSOLE_2026_REQUIRED_HEADERS):
        return FORMAT_CONSOLE_2026
    if all(header in headers for header in _LEGACY_REQUIRED_HEADERS):
        return FORMAT_CONSOLE_LEGACY
    return FORMAT_UNKNOWN


def _attribution_days(columns: Iterable) -> int:
    for header in _columns_by_header(columns):
        match = _ATTRIBUTION_HEADER.match(header)
        if match:
            return int(match.group(1))
    return DEFAULT_ATTRIBUTION_DAYS


def _text_column(table: pd.DataFrame, columns: Mapping[str, object], header: str) -> pd.Series:
    source = columns.get(header)
    if source is None:
        return pd.Series("", index=table.index, dtype=object)
    return table[source].fillna("").astype(str).str.strip()


def _number_column(table: pd.DataFrame, columns: Mapping[str, object], header: str) -> pd.Series:
    source = columns.get(header)
    if source is None:
        return pd.Series(0.0, index=table.index)
    text = table[source].fillna("").astype(str).str.strip()
    numbers = pd.to_numeric(text, errors="coerce")
    unparsed = numbers.isna() & text.ne("")
    if unparsed.any():
        log.warning("Column %r has %d non-numeric cells; they count as 0", source, int(unparsed.sum()))
    return numbers.fillna(0.0).astype("float64")


def _first_filled(values: pd.Series) -> str:
    filled = values[values.ne("")]
    return str(filled.iloc[0]) if not filled.empty else ""


def _single_account_file(file_format: str, table: pd.DataFrame, file_name: str, *, currency_code: str,
                         attribution_days: int) -> SearchTermFile:
    account = FileAccount(key=ALL_ACCOUNTS_KEY, name=file_name, currency_code=currency_code, row_count=len(table))
    return SearchTermFile(format=file_format, accounts=(account,), attribution_days=attribution_days,
                          account_frames={ALL_ACCOUNTS_KEY: table})


def _read_console_legacy(table: pd.DataFrame, file_name: str) -> SearchTermFile:
    columns = _columns_by_header(table.columns)
    attribution_days = _attribution_days(table.columns)
    currencies = _text_column(table, columns, "currency").map(valid_currency_code)
    distinct_currencies = sorted(set(currencies) - {""})
    if len(distinct_currencies) <= 1:
        return _single_account_file(FORMAT_CONSOLE_LEGACY, table, file_name,
                                    currency_code=distinct_currencies[0] if distinct_currencies else "",
                                    attribution_days=attribution_days)

    countries = _text_column(table, columns, "country").str.upper()
    accounts: list[FileAccount] = []
    account_frames: dict[str, pd.DataFrame] = {}
    for (currency, country), rows in table.groupby([currencies, countries], sort=True):
        key = f"{currency}:{country}"
        name = " · ".join(part for part in (country, currency) if part) or file_name
        accounts.append(FileAccount(key=key, name=name, currency_code=currency, row_count=len(rows)))
        account_frames[key] = rows.reset_index(drop=True)
    return SearchTermFile(format=FORMAT_CONSOLE_LEGACY, accounts=tuple(accounts),
                          attribution_days=attribution_days, account_frames=account_frames)


def _console_2026_frame(table: pd.DataFrame, columns: Mapping[str, object]) -> pd.DataFrame:
    frame = pd.DataFrame(index=table.index)
    for target, header in _CONSOLE_2026_TEXT_COLUMNS.items():
        frame[target] = _text_column(table, columns, header)
    for target in ("_campaign_id", "_ad_group_id"):
        frame[target] = _unwrap_excel_text(frame[target])
    # The 2026 export has neither match type nor targeting columns.
    frame[canonical.MATCH_TYPE] = ""
    frame[canonical.TARGETING] = ""
    for target, header in _CONSOLE_2026_COUNT_COLUMNS.items():
        frame[target] = _number_column(table, columns, header).round().astype("int64")
    for target, header in _CONSOLE_2026_AMOUNT_COLUMNS.items():
        frame[target] = _number_column(table, columns, header)
    return add_ratios(frame, CONSOLE_2026_ATTRIBUTION_DAYS)


def _read_console_2026(table: pd.DataFrame, file_name: str) -> SearchTermFile:
    columns = _columns_by_header(table.columns)
    frame = _console_2026_frame(table, columns)
    account_ids = _unwrap_excel_text(_text_column(table, columns, "advertiser account id"))
    account_names = _text_column(table, columns, "advertiser account name")
    currencies = _text_column(table, columns, "budget currency").map(valid_currency_code)

    if not account_ids.ne("").any() and len(_known_currencies(currencies)) <= 1:
        return _single_account_file(FORMAT_CONSOLE_2026, frame.reset_index(drop=True), file_name,
                                    currency_code=_first_filled(currencies),
                                    attribution_days=CONSOLE_2026_ATTRIBUTION_DAYS)

    accounts: list[FileAccount] = []
    account_frames: dict[str, pd.DataFrame] = {}
    for account_id in pd.unique(account_ids):
        in_account = account_ids.eq(account_id)
        key = account_id or UNIDENTIFIED_ACCOUNT_KEY
        name = _first_filled(account_names[in_account]) or account_id or file_name
        account_currencies = _known_currencies(currencies[in_account])
        if len(account_currencies) <= 1:
            groups = [(key, name, account_currencies[0] if account_currencies else "", in_account)]
        else:
            # One advertiser account can run several marketplaces; their amounts are never added together.
            groups = [
                (f"{key}:{currency or 'sin moneda'}", f"{name} · {currency or 'sin moneda'}", currency,
                 in_account & currencies.eq(currency))
                for currency in pd.unique(currencies[in_account])
            ]
        for group_key, group_name, currency, in_group in groups:
            accounts.append(FileAccount(key=group_key, name=group_name, currency_code=currency,
                                        row_count=int(in_group.sum())))
            account_frames[group_key] = frame[in_group].reset_index(drop=True)
    return SearchTermFile(format=FORMAT_CONSOLE_2026, accounts=tuple(accounts),
                          attribution_days=CONSOLE_2026_ATTRIBUTION_DAYS, account_frames=account_frames)


def _known_currencies(currencies: pd.Series) -> list[str]:
    return [currency for currency in pd.unique(currencies) if currency]


def _unwrap_excel_text(values: pd.Series) -> pd.Series:
    # The console writes ids as ="…" so Excel keeps them as text instead of rounding them.
    return values.str.replace(r'^="(.*)"$', r"\1", regex=True)

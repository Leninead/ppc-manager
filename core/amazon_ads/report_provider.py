"""Module-agnostic read API for synced Amazon Ads search-term data.

Reads `ads_profile_sync` and `search_terms_between` over PostgREST and returns the canonical console frame;
`ads_daily_totals` gives the same data summed by day.
"""
from __future__ import annotations

import hashlib
import io
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
import requests

from core import search_term_frame as canonical
from core.integrations.store import StoreError, _error_message, _Rest
from core.integrations.sync_jobs import parse_date, parse_timestamp
from core.search_term_frame import (
    ANY_WINDOW_PURCHASES,
    HIDDEN_ID_COLUMNS,
    PORTFOLIO_NAME_MISSING,
    SOURCE_API,
    SearchTermSource,
    add_ratios,
    console_columns,
    valid_currency_code,
)

log = logging.getLogger(__name__)

PROFILE_SYNC_TABLE = "ads_profile_sync"
SEARCH_TERMS_RPC = "search_terms_between"
DAILY_TOTALS_RPC = "ads_daily_totals"
READ_TIMEOUT_SECONDS = 120
SELLER_ATTRIBUTION_DAYS = 7
VENDOR_ATTRIBUTION_DAYS = 14
NOT_A_KEYWORD_MATCH = "-"

ORIGIN_BROAD = "BROAD"
ORIGIN_PHRASE = "PHRASE"
ORIGIN_EXACT = "EXACT"
ORIGIN_AUTO = "AUTO"
ORIGIN_PRODUCT_TARGETING = "PRODUCT_TARGETING"
KEYWORD_MATCH_TYPES = (ORIGIN_BROAD, ORIGIN_PHRASE, ORIGIN_EXACT)
_TARGETING_ORIGINS = {
    "TARGETING_EXPRESSION_PREDEFINED": ORIGIN_AUTO,
    "TARGETING_EXPRESSION": ORIGIN_PRODUCT_TARGETING,
}

_PROFILE_COLUMNS = (
    "profile_id,account_id,cliente,account_name,country_code,currency_code,account_type,"
    "timezone,status,data_from,data_through,refreshed_on,last_success_at,last_error"
)
_TEXT_FIELDS = ("campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting",
                "search_term", "campaign_name", "campaign_status", "ad_group_name", "keyword_text",
                "ad_keyword_status", "portfolio_id", "portfolio_name", "currency_code")
_COUNT_FIELDS = ("impressions", "clicks", "purchases_7d", "units_7d", "purchases_14d", "units_14d")
_AMOUNT_FIELDS = ("cost", "sales_7d", "sales_14d")
_RPC_FIELDS = _TEXT_FIELDS + _COUNT_FIELDS + _AMOUNT_FIELDS
_ATTRIBUTION_FIELDS = {
    SELLER_ATTRIBUTION_DAYS: ("sales_7d", "purchases_7d", "units_7d"),
    VENDOR_ATTRIBUTION_DAYS: ("sales_14d", "purchases_14d", "units_14d"),
}


class ReportReadError(StoreError):
    """Amazon Ads data could not be read; the message is ready to show to the user."""


@dataclass(frozen=True)
class DayTotals:
    day: date
    impressions: int
    clicks: int
    spend: float
    sales: float
    orders: int


@dataclass(frozen=True)
class DailySeries:
    """One profile's search-term totals per day, every day of the window present, zero where nothing ran."""

    days: tuple[DayTotals, ...]
    campaigns: tuple[str, ...]
    currency_code: str
    attribution_days: int


@dataclass(frozen=True)
class ProfileOption:
    profile_id: str
    account_id: int | None
    cliente: str
    account_name: str
    country_code: str
    currency_code: str
    account_type: str
    timezone: str
    status: str
    data_from: date | None
    data_through: date | None
    refreshed_on: date | None
    last_success_at: datetime | None
    last_error: str

    @property
    def label(self) -> str:
        return f"{self.cliente or self.account_name}"

    @classmethod
    def from_row(cls, row: dict) -> ProfileOption:
        account_id = row.get("account_id")
        return cls(
            profile_id=str(row.get("profile_id") or ""),
            account_id=int(account_id) if account_id is not None else None,
            cliente=row.get("cliente") or "",
            account_name=row.get("account_name") or "",
            country_code=(row.get("country_code") or "").upper(),
            currency_code=valid_currency_code(row.get("currency_code")),
            account_type=row.get("account_type") or "",
            timezone=row.get("timezone") or "",
            status=row.get("status") or "",
            data_from=parse_date(row.get("data_from")),
            data_through=parse_date(row.get("data_through")),
            refreshed_on=parse_date(row.get("refreshed_on")),
            last_success_at=parse_timestamp(row.get("last_success_at")),
            last_error=row.get("last_error") or "",
        )


class ReportProvider:
    def __init__(self, rest: _Rest):
        self._rest = rest

    def profiles(self) -> list[ProfileOption]:
        """Synced profiles that are not inactive, sorted by label then country."""
        try:
            rows = self._rest.select(PROFILE_SYNC_TABLE, {"select": _PROFILE_COLUMNS, "status": "neq.inactive"})
        except requests.RequestException as exc:
            raise ReportReadError(_error_message(exc, "leer las cuentas de Amazon Ads")) from exc
        options = [ProfileOption.from_row(row) for row in rows]
        return sorted(options, key=lambda option: (option.label.casefold(), option.country_code))

    def search_terms(self, option: ProfileOption, start: date, end: date) -> SearchTermSource:
        """One profile's search terms summed over [start, end], shaped as the canonical console frame."""
        if end < start:
            raise ValueError(f"search term range ends before it starts: {start}..{end}")
        try:
            csv_bytes = self._rest.rpc_csv(
                SEARCH_TERMS_RPC,
                {"p_profile_id": option.profile_id, "p_from": start.isoformat(), "p_to": end.isoformat()},
                timeout_s=READ_TIMEOUT_SECONDS,
            )
            totals = _read_totals(csv_bytes)
        except (requests.RequestException, ValueError) as exc:
            raise ReportReadError(_error_message(exc, "leer los search terms de Amazon Ads")) from exc

        attribution_days = _attribution_days(option.account_type)
        frame = _canonical_frame(totals, attribution_days)
        log.info("amazon ads search terms read: profile %s %s..%s, %d rows, %dd attribution",
                 option.profile_id, start, end, len(frame), attribution_days)
        return SearchTermSource(
            frame=frame,
            source=SOURCE_API,
            currency_code=option.currency_code or _single_currency(totals),
            label=f"{option.label} · {option.country_code}" if option.country_code else option.label,
            signature=_signature(option, start, end),
            attribution_days=attribution_days,
            bulk_ready=True,
            profile_id=option.profile_id,
            window_start=start,
            window_end=end,
        )


    def daily_totals(self, option: ProfileOption, start: date, end: date, campaign: str = "") -> DailySeries:
        """One profile's totals per day over [start, end]; with `campaign`, only campaigns whose name contains it."""
        if end < start:
            raise ValueError(f"daily totals range ends before it starts: {start}..{end}")
        fragment = campaign.strip() or None
        attribution_days = _attribution_days(option.account_type)
        try:
            rows = self._rest.rpc(
                DAILY_TOTALS_RPC,
                {"p_profile_id": option.profile_id, "p_from": start.isoformat(), "p_to": end.isoformat(),
                 "p_campaign": fragment},
                timeout_s=READ_TIMEOUT_SECONDS,
            ) or []
            by_day = {totals.day: totals for totals in (_day_totals(row, attribution_days) for row in rows)}
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            raise ReportReadError(_error_message(exc, "leer la serie diaria de Amazon Ads")) from exc

        days = tuple(by_day.get(day) or DayTotals(day, 0, 0, 0.0, 0.0, 0) for day in _each_day(start, end))
        campaigns = sorted({name for row in rows for name in row.get("campaign_names") or ()}) if fragment else []
        currencies = {valid_currency_code(row.get("currency_code")) for row in rows} - {""}
        return DailySeries(
            days=days,
            campaigns=tuple(campaigns),
            currency_code=option.currency_code or (currencies.pop() if len(currencies) == 1 else ""),
            attribution_days=attribution_days,
        )


def account_labels(profiles: list[ProfileOption]) -> dict[str, str]:
    """Client and country, plus the account type when one client has two profiles in the same country."""
    repeated = Counter((profile.label, profile.country_code) for profile in profiles)
    labels = {}
    for profile in profiles:
        label = f"{profile.label} · {profile.country_code}" if profile.country_code else profile.label
        if repeated[(profile.label, profile.country_code)] > 1:
            label += f" · {profile.account_type or profile.account_name or profile.profile_id}"
        labels[profile.profile_id] = label
    return labels


def _day_totals(row: dict, attribution_days: int) -> DayTotals:
    sales_field, orders_field, _ = _ATTRIBUTION_FIELDS[attribution_days]
    return DayTotals(
        day=date.fromisoformat(str(row["report_date"])),
        impressions=int(row.get("impressions") or 0),
        clicks=int(row.get("clicks") or 0),
        spend=float(row.get("cost") or 0),
        sales=float(row.get(sales_field) or 0),
        orders=int(row.get(orders_field) or 0),
    )


def _each_day(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _attribution_days(account_type: str) -> int:
    # Vendor accounts report 14-day attribution in the console; sellers use 7 days.
    if account_type.strip().casefold() == "vendor":
        return VENDOR_ATTRIBUTION_DAYS
    return SELLER_ATTRIBUTION_DAYS


def _signature(option: ProfileOption, start: date, end: date) -> str:
    fingerprint = f"{option.profile_id}|{start}|{end}|{option.last_success_at}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]


def _read_totals(csv_bytes: bytes) -> pd.DataFrame:
    """The RPC answer with text fields as str and metric fields parsed; raises ValueError on a malformed answer."""
    if csv_bytes.strip():
        # keep_default_na=False: a search term like "NA" or "null" is text, not a missing value.
        totals = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="utf-8")
    else:
        totals = pd.DataFrame({field: pd.Series(dtype=str) for field in _RPC_FIELDS})
    missing = [field for field in _RPC_FIELDS if field not in totals.columns]
    if missing:
        raise ValueError(f"{SEARCH_TERMS_RPC} answered without columns {missing}")
    for field in _TEXT_FIELDS:
        # PostgREST writes text/csv from record_out, which doubles every backslash inside a field.
        totals[field] = totals[field].str.replace("\\\\", "\\", regex=False)
    for field in _COUNT_FIELDS:
        totals[field] = _numbers(totals, field).round().astype("int64")
    for field in _AMOUNT_FIELDS:
        totals[field] = _numbers(totals, field).astype("float64")
    return totals


def _canonical_frame(totals: pd.DataFrame, attribution_days: int) -> pd.DataFrame:
    sales_field, orders_field, units_field = _ATTRIBUTION_FIELDS[attribution_days]
    origins = [_origin_match_type(match_type, keyword_type)
               for match_type, keyword_type in zip(totals["match_type"], totals["keyword_type"])]
    frame = pd.DataFrame({
        canonical.SEARCH_TERM: totals["search_term"],
        canonical.CAMPAIGN_NAME: totals["campaign_name"],
        canonical.AD_GROUP_NAME: totals["ad_group_name"],
        canonical.PORTFOLIO_NAME: [_portfolio_label(portfolio_id, name) for portfolio_id, name
                                   in zip(totals["portfolio_id"], totals["portfolio_name"])],
        canonical.MATCH_TYPE: [origin if origin in KEYWORD_MATCH_TYPES else NOT_A_KEYWORD_MATCH
                               for origin in origins],
        canonical.TARGETING: totals["targeting"],
        canonical.IMPRESSIONS: totals["impressions"],
        canonical.CLICKS: totals["clicks"],
        canonical.SPEND: totals["cost"],
        canonical.sales_column(attribution_days): totals[sales_field],
        canonical.orders_column(attribution_days): totals[orders_field],
        canonical.units_column(attribution_days): totals[units_field],
        "_campaign_id": totals["campaign_id"],
        "_ad_group_id": totals["ad_group_id"],
        "_keyword_id": totals["keyword_id"],
        "_keyword_type": totals["keyword_type"],
        "_origin_match_type": origins,
        "_campaign_status": totals["campaign_status"],
        "_ad_keyword_status": totals["ad_keyword_status"],
        "_keyword_text": totals["keyword_text"],
        ANY_WINDOW_PURCHASES: totals[["purchases_7d", "purchases_14d"]].max(axis=1).astype("int64"),
        PORTFOLIO_NAME_MISSING: [bool(portfolio_id.strip()) and not name.strip() for portfolio_id, name
                                 in zip(totals["portfolio_id"], totals["portfolio_name"])],
    })
    # The RPC returns ties in no fixed order; the ids break them so one data version always reads the same.
    frame = frame.sort_values(
        [canonical.SPEND, canonical.CLICKS, canonical.SEARCH_TERM, "_campaign_id", "_ad_group_id", "_keyword_type",
         "_keyword_id", "_origin_match_type", canonical.TARGETING],
        ascending=[False, False, True, True, True, True, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    with_ratios = add_ratios(frame, attribution_days)
    return with_ratios[console_columns(attribution_days) + list(HIDDEN_ID_COLUMNS)]


def _origin_match_type(match_type: str, keyword_type: str) -> str:
    for raw in (match_type, keyword_type):
        value = raw.strip().upper()
        if value in KEYWORD_MATCH_TYPES:
            return value
        if value in _TARGETING_ORIGINS:
            return _TARGETING_ORIGINS[value]
    return ""


def _portfolio_label(portfolio_id: str, name: str) -> str:
    if name.strip():
        return name.strip()
    return f"Portfolio {portfolio_id.strip()}" if portfolio_id.strip() else ""


def _numbers(totals: pd.DataFrame, field: str) -> pd.Series:
    raw = totals[field].astype(str).str.strip()
    parsed = pd.to_numeric(raw, errors="coerce")
    unreadable = parsed.isna() & raw.ne("")
    if unreadable.any():
        raise ValueError(f"{SEARCH_TERMS_RPC} answered a non-numeric {field}: {raw[unreadable].iloc[0]!r}")
    return parsed.fillna(0)


def _single_currency(totals: pd.DataFrame) -> str:
    currencies = {valid_currency_code(code) for code in totals["currency_code"]} - {""}
    return currencies.pop() if len(currencies) == 1 else ""

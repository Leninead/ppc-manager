"""The write path of Seller Central data over PostgREST, for the app and for the SP-API worker.

The database decides everything (migration 023): which account a profile belongs to, what a period holds, what a
write replaces and what needs confirmation. This module sends rows and reads the answer. Every write can run as a
preview that changes nothing and returns the same answer, which is what the confirmation dialog shows.
"""
from __future__ import annotations

import logging
import math
import numbers
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import requests

from core.integrations.store import _Rest, _rest_credentials
from core.seller_reports.periods import SqpPeriod

log = logging.getLogger(__name__)

MANUAL = "manual"
SP_API = "sp_api"

INSERTED = "inserted"
REPLACED = "replaced"
UNCHANGED = "unchanged"
CONFLICT = "conflict"
DELETED = "deleted"
RESTORED = "restored"
REMOVED = "removed"
SKIPPED = "skipped"

_REJECTION_PREFIX = "seller_report."
_WRITE_TIMEOUT_S = 60


class SellerReportRejected(ValueError):
    """The database refused the call: the rows, the period or the account are not valid for it."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SellerAccount:
    id: int
    ads_entity_id: str
    marketplace_id: str
    country_code: str
    account_name: str
    selling_partner_id: str | None
    selling_partner_id_source: str


@dataclass(frozen=True)
class PeriodChange:
    """What a call did, or would do in a preview, to one period; existing_* describe it before the call."""

    period_start: date
    period_end: date
    brand_or_asin: str
    status: str
    row_count: int
    existing_source: str | None
    existing_row_count: int | None
    existing_loaded_by: str | None
    existing_loaded_at: datetime | None
    existing_file_name: str | None
    load_id: int | None


@dataclass(frozen=True)
class LoadResult:
    changes: tuple[PeriodChange, ...]

    @property
    def load_id(self) -> int | None:
        """The load the call wrote or undid; None when it wrote nothing."""
        return next((change.load_id for change in self.changes if change.load_id is not None), None)

    @property
    def conflicts(self) -> tuple[PeriodChange, ...]:
        """The periods whose SP-API data the call would overwrite or delete: the call waits for confirmation."""
        return tuple(change for change in self.changes if change.status == CONFLICT)


class SellerReportStore:
    def __init__(self, rest: _Rest):
        self._rest = rest

    def account_for_ads_profile(self, profile_id: str, actor: str = "") -> SellerAccount:
        """The seller account of an Amazon Ads profile, created the first time it is asked for."""
        return _to_seller_account(self._call("seller_account_for_ads_profile",
                                             {"p_profile_id": profile_id, "p_actor": actor}))

    def set_selling_partner_id(self, account_id: int, selling_partner_id: str | None,
                               actor: str = "") -> SellerAccount:
        """Sets the account's SP-API seller id by hand; None clears it."""
        return _to_seller_account(self._call("set_selling_partner_id", {
            "p_account_id": account_id, "p_selling_partner_id": selling_partner_id, "p_actor": actor}))

    def delete_account(self, account_id: int) -> bool:
        """Deletes an account with no data left. False when it no longer exists."""
        return bool(self._call("delete_seller_account", {"p_account_id": account_id}))

    def upload_sales_traffic_daily(self, account_id: int, rows: Iterable[Mapping], *, preview: bool = False,
                                   replace_api_data: bool = False, loaded_by: str = "",
                                   file_name: str = "") -> LoadResult:
        return self._write("upload_seller_sales_traffic_daily",
                           {"p_account_id": account_id, "p_rows": _json_rows(rows)},
                           preview=preview, replace_api_data=replace_api_data, loaded_by=loaded_by,
                           file_name=file_name)

    def upload_sales_traffic_by_asin(self, account_id: int, first_day: date, last_day: date, rows: Iterable[Mapping],
                                     *, preview: bool = False, replace_api_data: bool = False, loaded_by: str = "",
                                     file_name: str = "") -> LoadResult:
        return self._write("upload_seller_sales_traffic_by_asin",
                           {"p_account_id": account_id, "p_range_start": first_day.isoformat(),
                            "p_range_end": last_day.isoformat(), "p_rows": _json_rows(rows)},
                           preview=preview, replace_api_data=replace_api_data, loaded_by=loaded_by,
                           file_name=file_name)

    def upload_search_query_performance(self, account_id: int, view: str, brand_or_asin: str, period: SqpPeriod,
                                        rows: Iterable[Mapping], *, preview: bool = False,
                                        replace_api_data: bool = False, loaded_by: str = "",
                                        file_name: str = "") -> LoadResult:
        return self._write("upload_seller_search_query_performance",
                           {"p_account_id": account_id, "p_view": view, "p_brand_or_asin": brand_or_asin,
                            "p_period_type": period.period_type, "p_period_start": period.start.isoformat(),
                            "p_rows": _json_rows(rows)},
                           preview=preview, replace_api_data=replace_api_data, loaded_by=loaded_by,
                           file_name=file_name)

    def save_sales_traffic_daily(self, account_id: int, rows: Iterable[Mapping], *, preview: bool = False,
                                 loaded_by: str = "") -> LoadResult:
        """The SP-API worker's write: its data replaces what a period holds without asking."""
        return self._write("save_seller_sales_traffic_daily",
                           {"p_account_id": account_id, "p_rows": _json_rows(rows), "p_source": SP_API},
                           preview=preview, loaded_by=loaded_by)

    def save_sales_traffic_by_asin(self, account_id: int, first_day: date, last_day: date, rows: Iterable[Mapping],
                                   *, preview: bool = False, loaded_by: str = "") -> LoadResult:
        return self._write("save_seller_sales_traffic_by_asin",
                           {"p_account_id": account_id, "p_range_start": first_day.isoformat(),
                            "p_range_end": last_day.isoformat(), "p_rows": _json_rows(rows), "p_source": SP_API},
                           preview=preview, loaded_by=loaded_by)

    def save_search_query_performance(self, account_id: int, view: str, brand_or_asin: str, period: SqpPeriod,
                                      rows: Iterable[Mapping], *, preview: bool = False,
                                      loaded_by: str = "") -> LoadResult:
        return self._write("save_seller_search_query_performance",
                           {"p_account_id": account_id, "p_view": view, "p_brand_or_asin": brand_or_asin,
                            "p_period_type": period.period_type, "p_period_start": period.start.isoformat(),
                            "p_rows": _json_rows(rows), "p_source": SP_API},
                           preview=preview, loaded_by=loaded_by)

    def delete_periods(self, account_id: int, dataset: str, brand_or_asin: str, first_day: date, last_day: date,
                       *, preview: bool = False, replace_api_data: bool = False,
                       deleted_by: str = "") -> LoadResult:
        """Deletes the periods of a dataset inside the range; the delete is a load, so it can be undone."""
        return _to_load_result(self._call("delete_seller_report_periods", {
            "p_account_id": account_id, "p_dataset": dataset, "p_brand_or_asin": brand_or_asin,
            "p_first_day": first_day.isoformat(), "p_last_day": last_day.isoformat(),
            "p_replace_api_data": replace_api_data, "p_preview": preview, "p_deleted_by": deleted_by}))

    def revert_load(self, load_id: int, *, preview: bool = False, reverted_by: str = "") -> LoadResult:
        """Undoes a load: each period it still owns goes back to what it held before it."""
        return _to_load_result(self._call("revert_seller_report_load", {
            "p_load_id": load_id, "p_preview": preview, "p_reverted_by": reverted_by}))

    def _write(self, function: str, args: dict, *, preview: bool, replace_api_data: bool = False,
               loaded_by: str = "", file_name: str = "") -> LoadResult:
        return _to_load_result(self._call(function, {
            **args, "p_replace_api_data": replace_api_data, "p_preview": preview, "p_loaded_by": loaded_by,
            "p_file_name": file_name}))

    def _call(self, function: str, args: dict):
        try:
            return self._rest.rpc(function, args, timeout_s=_WRITE_TIMEOUT_S)
        except requests.HTTPError as exc:
            rejection = _rejection(exc.response)
            if rejection is None:
                status = exc.response.status_code if exc.response is not None else "no response"
                log.error("seller_reports: %s failed (%s)", function, status)
                raise
            log.info("seller_reports: %s refused (%s)", function, rejection.code)
            raise rejection from exc


def open_seller_report_store() -> SellerReportStore | None:
    """The app's store, or None when no database is configured."""
    credentials = _rest_credentials()
    return SellerReportStore(_Rest(*credentials)) if credentials else None


def _json_rows(rows: Iterable[Mapping]) -> list[dict]:
    return [{str(column): _json_value(value) for column, value in row.items()} for row in rows]


def _json_value(value):
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return None
        # pandas reads a count next to an empty cell as 12.0, and an integer column refuses "12.0".
        return int(number) if number.is_integer() else number
    raise TypeError(f"a Seller Central row cannot carry a {type(value).__name__}")


def _rejection(response: requests.Response | None) -> SellerReportRejected | None:
    if response is None:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    message = str(body.get("message") or "") if isinstance(body, dict) else ""
    if not message.startswith(_REJECTION_PREFIX):
        return None
    return SellerReportRejected(message[len(_REJECTION_PREFIX):], str(body.get("details") or ""))


def _to_seller_account(row: Mapping) -> SellerAccount:
    return SellerAccount(
        id=int(row["id"]),
        ads_entity_id=row["ads_entity_id"],
        marketplace_id=row["marketplace_id"],
        country_code=row.get("country_code") or "",
        account_name=row.get("account_name") or "",
        selling_partner_id=row.get("selling_partner_id"),
        selling_partner_id_source=row.get("selling_partner_id_source") or "",
    )


def _to_load_result(rows) -> LoadResult:
    return LoadResult(tuple(_to_period_change(row) for row in rows or ()))


def _to_period_change(row: Mapping) -> PeriodChange:
    loaded_at = row.get("existing_loaded_at")
    return PeriodChange(
        period_start=date.fromisoformat(row["period_start"]),
        period_end=date.fromisoformat(row["period_end"]),
        brand_or_asin=row.get("brand_or_asin") or "",
        status=row["status"],
        row_count=int(row.get("row_count") or 0),
        existing_source=row.get("existing_source"),
        existing_row_count=row.get("existing_row_count"),
        existing_loaded_by=row.get("existing_loaded_by"),
        existing_loaded_at=datetime.fromisoformat(loaded_at) if loaded_at else None,
        existing_file_name=row.get("existing_file_name"),
        load_id=row.get("load_id"),
    )

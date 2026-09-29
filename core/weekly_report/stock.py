"""Stock per ASIN for the Weekly Client Report, from the client's latest Pricing Dashboard snapshot.

The snapshot has one row per SKU and the report one row per child ASIN, so the SKUs of an ASIN add up. A SKU without an
ASIN cannot reach a report row: it is counted, not guessed. A missing value stays None and is never shown as 0, which
is reserved for a snapshot that says the shelf is empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from core.persistence import _list_periods, _load_snapshot

AREA = "account-health"
MODULE = "pricing-dashboard"
STOCK_FIELDS = (("fba", "fba_available"), ("awd", "awd_available"), ("izzi", "izzi_available"),
                ("total", "total_stock"))
REPORT_COLUMNS = (("fba", "FBA"),)
"""The stock columns the report shows. The Pricing Dashboard saves AWD and Izzi as 0 until it integrates them, so
they stay out; add ("awd", "AWD"), ("izzi", "Izzi") and ("total", "Total") here once it saves them for real."""


@dataclass(frozen=True)
class AsinStock:
    """Units of one ASIN, or of the account, by where they sit; None when the snapshot did not say."""

    fba: float | None = None
    awd: float | None = None
    izzi: float | None = None
    total: float | None = None


@dataclass(frozen=True)
class StockSnapshot:
    """The stock the report can show: the snapshot's date (None without one), its ASINs and the SKUs left out."""

    snapshot_date: str | None = None
    by_asin: dict[str, AsinStock] = field(default_factory=dict)
    skus_without_asin: int = 0
    account: AsinStock = AsinStock()

    def for_asin(self, asin: str) -> AsinStock:
        return self.by_asin.get(_asin_key(asin), AsinStock())


def stock_by_asin(snapshot: pd.DataFrame | None, snapshot_date: str | None) -> StockSnapshot:
    """Adds up each ASIN's SKUs; the account row adds up every ASIN the snapshot has."""
    if snapshot is None:
        return StockSnapshot()
    if snapshot.empty or "asin" not in snapshot.columns:
        return StockSnapshot(snapshot_date=snapshot_date, skus_without_asin=len(snapshot))
    asins = snapshot["asin"].map(_asin_key)
    with_asin = snapshot[asins != ""].assign(_asin=asins[asins != ""])
    values = pd.DataFrame({name: _units(with_asin, column) for name, column in STOCK_FIELDS})
    values["_asin"] = with_asin["_asin"]
    grouped = values.groupby("_asin").sum(min_count=1)
    by_asin = {asin: _stock_of(row) for asin, row in grouped.iterrows()}
    account = _stock_of(values.drop(columns="_asin").sum(min_count=1)) if not values.empty else AsinStock()
    return StockSnapshot(snapshot_date=snapshot_date, by_asin=by_asin,
                         skus_without_asin=int((asins == "").sum()), account=account)


def latest_stock(cliente: str) -> StockSnapshot:
    """The client's latest Pricing Dashboard snapshot as report stock; no snapshot gives no date and no ASINs."""
    periods = _list_periods(AREA, cliente, MODULE)
    if not periods:
        return StockSnapshot()
    latest = periods[-1]
    return stock_by_asin(_load_snapshot(AREA, cliente, MODULE, latest), latest)


def days_before_week(snapshot_date: str | None, week_start: str | None) -> int | None:
    """How many days the snapshot predates the report's week; None when it falls inside or either date is unknown."""
    if not snapshot_date or not week_start:
        return None
    gap = (date.fromisoformat(week_start[:10]) - date.fromisoformat(snapshot_date[:10])).days
    return gap if gap > 0 else None


def _asin_key(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().upper()


def _units(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def _stock_of(row: pd.Series) -> AsinStock:
    return AsinStock(**{name: (None if pd.isna(row[name]) else float(row[name])) for name, _ in STOCK_FIELDS})

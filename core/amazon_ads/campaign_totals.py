"""Totals of Sponsored Products, Brands and Display campaigns by day or by campaign, for the chat.

Read from the campaign reports (`campaign_daily_totals`, `campaign_window_totals`, migration 015), not from
the search terms, which only carry terms with clicks. Sales and orders are each product's own, as Campaign
Manager shows them: SP after a click (7 or 14 days, by account type), SB and SD after a click or a view (14
days). The click-only ones travel apart, so products can be compared on the same basis.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from core.amazon_ads.product_provider import NewToBrand
from core.amazon_ads.report_provider import (
    READ_TIMEOUT_SECONDS,
    SELLER_ATTRIBUTION_DAYS,
    ProfileOption,
    ReportReadError,
    _attribution_days,
    _each_day,
    _is_missing_function,
    _portfolio_label,
)
from core.integrations.store import _error_message, _Rest
from core.search_term.frame import valid_currency_code

DAILY_TOTALS_RPC = "campaign_daily_totals"
WINDOW_TOTALS_RPC = "campaign_window_totals"
BY_CAMPAIGN_RPC = "campaign_daily_totals_by_campaign"
PRODUCTS = ("SP", "SB", "SD")
# The products whose reports credit new-to-brand customers.
NEW_TO_BRAND_PRODUCTS = ("SB", "SD")
NEW_TO_BRAND_COLUMNS = ("ntb_orders", "ntb_sales")


@dataclass(frozen=True)
class Totals:
    spend: float
    sales: float
    orders: int
    clicks: int
    impressions: int
    sales_clicks: float
    orders_clicks: int


@dataclass(frozen=True)
class ProductDay:
    day: date
    totals: Totals


@dataclass(frozen=True)
class ProductSeries:
    """Every day of the window, zero where nothing ran, over the products asked for."""

    days: tuple[ProductDay, ...]
    campaigns: tuple[str, ...]
    products: tuple[str, ...]
    currency_code: str
    attribution_days: int
    # Aligned with `days` when the series is SB or SD alone; None on a day whose rows were never measured.
    new_to_brand: tuple[NewToBrand | None, ...] = ()


def daily_totals(rest: _Rest, option: ProfileOption, start: date, end: date, *, campaign: str = "",
                 product: str = "") -> ProductSeries:
    """One profile's totals per day; `product` narrows them to SP, SB or SD, `campaign` to names containing it."""
    if end < start:
        raise ValueError(f"daily totals range ends before it starts: {start}..{end}")
    fragment = campaign.strip() or None
    attribution_days = _attribution_days(option.account_type)
    try:
        rows = rest.rpc(DAILY_TOTALS_RPC, {"p_profile_id": option.profile_id, "p_from": start.isoformat(),
                                           "p_to": end.isoformat(), "p_campaign": fragment},
                        timeout_s=READ_TIMEOUT_SECONDS) or []
        rows = [row for row in rows if not product or row.get("ad_product") == product]
        by_day: dict[date, list[Totals]] = {}
        for row in rows:
            by_day.setdefault(date.fromisoformat(str(row["report_date"])), []).append(_totals(row, attribution_days))
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        raise ReportReadError(_error_message(exc, "leer la serie diaria de campañas de Amazon Ads")) from exc

    days = tuple(ProductDay(day, _sum(by_day.get(day, []))) for day in _each_day(start, end))
    names = sorted({name for row in rows for name in row.get("campaign_names") or () if name}) if fragment else []
    currencies = {valid_currency_code(row.get("currency_code")) for row in rows} - {""}
    return ProductSeries(
        days=days,
        campaigns=tuple(names),
        products=tuple(code for code in PRODUCTS if any(row.get("ad_product") == code for row in rows)),
        currency_code=option.currency_code or (currencies.pop() if len(currencies) == 1 else ""),
        attribution_days=attribution_days,
        new_to_brand=_daily_new_to_brand(rows, start, end) if product in NEW_TO_BRAND_PRODUCTS else (),
    )


def _daily_new_to_brand(rows: list[dict], start: date, end: date) -> tuple[NewToBrand | None, ...]:
    """Each day's new-to-brand figures of one product's rows; a day without rows sold none to anyone."""
    by_day = {date.fromisoformat(str(row["report_date"])): new_to_brand(row) for row in rows}
    return tuple(by_day.get(day, NewToBrand(0, 0.0)) for day in _each_day(start, end))


def new_to_brand(row: dict) -> NewToBrand | None:
    """A row's new-to-brand figures, or None when the row does not know them."""
    orders, sales = row.get("new_to_brand_purchases"), row.get("new_to_brand_sales")
    if orders in (None, "") or sales in (None, ""):
        return None
    return NewToBrand(_int(orders), _float(sales))


def sum_new_to_brand(parts) -> NewToBrand | None:
    """The sum of several figures; unknown when any of them is."""
    parts = list(parts)
    if any(part is None for part in parts):
        return None
    return NewToBrand(sum(part.orders for part in parts), round(sum(part.sales for part in parts), 2))


def daily_totals_by_campaign(rest: _Rest, option: ProfileOption, start: date, end: date,
                             campaign_ids: tuple[str, ...]) -> pd.DataFrame | None:
    """One row per campaign and day of the campaigns asked for by id; None while the database lacks migration 019.

    Columns: day, product, campaign_id, the fields of Totals and the new-to-brand figures (NaN where unmeasured).
    """
    if end < start:
        raise ValueError(f"campaign daily totals range ends before it starts: {start}..{end}")
    columns = ["day", "product", "campaign_id", *Totals.__dataclass_fields__, *NEW_TO_BRAND_COLUMNS]
    if not campaign_ids:
        return pd.DataFrame(columns=columns)
    attribution_days = _attribution_days(option.account_type)
    try:
        rows = rest.rpc(BY_CAMPAIGN_RPC, {"p_profile_id": option.profile_id, "p_from": start.isoformat(),
                                          "p_to": end.isoformat(), "p_campaign_ids": list(campaign_ids)},
                        timeout_s=READ_TIMEOUT_SECONDS) or []
        records = [{"day": date.fromisoformat(str(row["report_date"])), "product": row["ad_product"],
                    "campaign_id": str(row["campaign_id"]), **vars(_totals(row, attribution_days)),
                    **_new_to_brand_columns(row)} for row in rows]
    except requests.HTTPError as exc:
        if _is_missing_function(exc):
            return None
        raise ReportReadError(_error_message(exc, "leer la serie diaria por campaña de Amazon Ads")) from exc
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        raise ReportReadError(_error_message(exc, "leer la serie diaria por campaña de Amazon Ads")) from exc
    return pd.DataFrame(records, columns=columns)


def _new_to_brand_columns(row: dict) -> dict:
    figures = new_to_brand(row) if row.get("ad_product") in NEW_TO_BRAND_PRODUCTS else None
    if figures is None:
        return dict.fromkeys(NEW_TO_BRAND_COLUMNS, float("nan"))
    return {"ntb_orders": figures.orders, "ntb_sales": figures.sales}


def series_total(series: ProductSeries) -> Totals:
    """The whole window's totals."""
    return _sum([day.totals for day in series.days])


def window_totals(rest: _Rest, option: ProfileOption, start: date, end: date) -> pd.DataFrame:
    """One row per campaign with activity in the range: product, id, campaign, portfolio, its totals and its
    new-to-brand figures (NaN for SP, and where a day was never measured)."""
    if end < start:
        raise ValueError(f"window totals range ends before it starts: {start}..{end}")
    attribution_days = _attribution_days(option.account_type)
    try:
        csv_bytes = rest.rpc_csv(WINDOW_TOTALS_RPC, {"p_profile_id": option.profile_id, "p_from": start.isoformat(),
                                                     "p_to": end.isoformat()}, timeout_s=READ_TIMEOUT_SECONDS)
        raw = (pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="utf-8")
               if csv_bytes.strip() else pd.DataFrame())
        records = [{
            "product": row["ad_product"],
            "campaign_id": row["campaign_id"],
            "campaign": row["campaign_name"].replace("\\\\", "\\").strip() or f"Campaña {row['campaign_id']}",
            "portfolio": _portfolio_label(row["portfolio_id"], row["portfolio_name"].replace("\\\\", "\\")),
            **vars(_totals(row, attribution_days)),
            **_new_to_brand_columns(row),
        } for row in raw.to_dict("records")]
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        raise ReportReadError(_error_message(exc, "leer los totales por campaña de Amazon Ads")) from exc
    frame = pd.DataFrame(records, columns=["product", "campaign_id", "campaign", "portfolio",
                                           *Totals.__dataclass_fields__, *NEW_TO_BRAND_COLUMNS])
    # The reports keep an all-zero row for a campaign that served nothing: that is no activity.
    return frame[frame[list(Totals.__dataclass_fields__)].ne(0).any(axis=1)].reset_index(drop=True)


def _totals(row: dict, attribution_days: int) -> Totals:
    """SP's sales and orders in the account's attribution; SB's and SD's as Campaign Manager counts them."""
    window = "7d" if attribution_days == SELLER_ATTRIBUTION_DAYS else "14d"
    if row.get("ad_product") == "SP":
        sales, orders = _float(row.get(f"sales_{window}")), _int(row.get(f"purchases_{window}"))
        sales_clicks, orders_clicks = sales, orders
    else:
        sales, orders = _float(row.get("sales")), _int(row.get("purchases"))
        sales_clicks, orders_clicks = _float(row.get("sales_clicks")), _int(row.get("purchases_clicks"))
    return Totals(spend=_float(row.get("cost")), sales=sales, orders=orders, clicks=_int(row.get("clicks")),
                  impressions=_int(row.get("impressions")), sales_clicks=sales_clicks, orders_clicks=orders_clicks)


def _sum(parts: list[Totals]) -> Totals:
    return Totals(**{field: sum(getattr(part, field) for part in parts) for field in Totals.__dataclass_fields__})


def _float(value) -> float:
    return float(value) if value not in (None, "") else 0.0


def _int(value) -> int:
    return int(round(float(value))) if value not in (None, "") else 0

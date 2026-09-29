"""The Weekly Client Report's Advertising sheet, from the account's campaign totals over the report's days.

It carries what the Campaign CSV the module used to ask for carried, read from the synced campaign reports: Sponsored
Products, Brands and Display as Campaign Manager counts them. New-to-brand comes from Brands and Display, the products
whose reports credit it; detail page views are not synced, so the sheet leaves them unknown.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.campaign_totals import NEW_TO_BRAND_PRODUCTS, sum_new_to_brand
from core.amazon_ads.product_provider import NewToBrand

TOP_CAMPAIGNS = 15
ALARM_ACOS = 60.0
NO_PORTFOLIO = "(Sin Portfolio)"


@dataclass(frozen=True)
class Advertising:
    """The account's advertising over the report's days: totals, top campaigns, their alarms and the portfolios."""

    totals: dict                    # Impressions, Clicks, Spend, Sales, Orders, CTR, CPC and ACoS (None without sales)
    new_to_brand: NewToBrand | None  # SB and SD together; None when none ran or a day of theirs was never measured
    new_to_brand_share: float | None  # new-to-brand orders over SB and SD orders, as a percentage
    campaigns: list[dict]           # the most spend first, up to TOP_CAMPAIGNS
    alarms: list[dict]              # the top campaigns over ALARM_ACOS, or with spend and no sales
    portfolios: list[dict]          # the most spend first
    campaign_count: int             # every campaign with activity


def advertising_summary(totals: pd.DataFrame) -> Advertising:
    """`totals` has one row per campaign with activity, as the account's campaign totals over a window return it."""
    sums = {field: float(totals[column].sum()) for field, column in (
        ("Impressions", "impressions"), ("Clicks", "clicks"), ("Spend", "spend"), ("Sales", "sales"),
        ("Orders", "orders"))}
    sums.update(CTR=_percent(sums["Clicks"], sums["Impressions"]),
                CPC=round(sums["Spend"] / sums["Clicks"], 2) if sums["Clicks"] else None,
                ACoS=_percent(sums["Spend"], sums["Sales"]))
    new_to_brand, share = _new_to_brand(totals)
    # The read comes in no set order: ties are broken by product and id so the same data lists the same way.
    ordered = totals.sort_values(["spend", "product", "campaign_id"], ascending=[False, True, True], kind="stable")
    campaigns = [_campaign_row(row) for row in ordered.head(TOP_CAMPAIGNS).itertuples(index=False)]
    alarms = [campaign for campaign in campaigns if campaign["Spend"] > 0
              and (campaign["ACoS"] is None or campaign["ACoS"] > ALARM_ACOS)]
    return Advertising(totals=sums, new_to_brand=new_to_brand, new_to_brand_share=share, campaigns=campaigns,
                       alarms=alarms, portfolios=_portfolio_rows(totals), campaign_count=len(totals))


def _new_to_brand(totals: pd.DataFrame) -> tuple[NewToBrand | None, float | None]:
    brand = totals[totals["product"].isin(NEW_TO_BRAND_PRODUCTS)]
    if brand.empty:
        return None, None
    figures = sum_new_to_brand(None if _missing(orders) or _missing(sales) else NewToBrand(int(orders), float(sales))
                               for orders, sales in zip(brand["ntb_orders"], brand["ntb_sales"]))
    if figures is None:
        return None, None
    return figures, _percent(figures.orders, float(brand["orders"].sum()))


def _campaign_row(row) -> dict:
    return {"Campaign": row.campaign, "Product": row.product, "Impressions": int(row.impressions),
            "Clicks": int(row.clicks), "CTR": _percent(row.clicks, row.impressions),
            "Spend": round(float(row.spend), 2), "Sales": round(float(row.sales), 2),
            "ACoS": _percent(row.spend, row.sales, 1), "Orders": int(row.orders)}


def _portfolio_rows(totals: pd.DataFrame) -> list[dict]:
    named = totals.assign(portfolio=totals["portfolio"].replace("", NO_PORTFOLIO))
    grouped = named.groupby("portfolio", as_index=False)[["spend", "sales"]].sum()
    grouped = grouped.sort_values(["spend", "portfolio"], ascending=[False, True], kind="stable")
    return [{"Portfolio": row.portfolio, "Spend": round(float(row.spend), 2), "Sales": round(float(row.sales), 2),
             "ACoS": _percent(row.spend, row.sales, 1)} for row in grouped.itertuples(index=False)]


def _percent(part: float, whole: float, decimals: int = 2) -> float | None:
    """`part` over `whole` as a percentage, None when there is no whole."""
    return round(part / whole * 100, decimals) if whole else None


def _missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))

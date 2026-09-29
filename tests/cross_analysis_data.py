"""Synthetic Amazon Ads search terms and SQP rows for the Análisis Cruzado tests.

The search terms go through the real ReportProvider, so every test reads the canonical frame the page reads.
"""
import csv
import io
from datetime import date

import pandas as pd

from core.amazon_ads.report_provider import ProfileOption, ReportProvider

SEARCH_TERM_COLUMNS = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting",
                       "search_term", "campaign_name", "campaign_status", "ad_group_name", "keyword_text",
                       "ad_keyword_status", "portfolio_id", "portfolio_name", "currency_code", "impressions", "clicks",
                       "purchases_7d", "units_7d", "purchases_14d", "units_14d", "cost", "sales_7d", "sales_14d"]
PROFILE = ProfileOption.from_row({"profile_id": "111", "cliente": "Luna Kids", "country_code": "US",
                                  "currency_code": "USD", "account_type": "seller", "status": "active"})
START, END = date(2026, 9, 1), date(2026, 9, 27)


def term_row(text: str, *, campaign_id: str = "3001", ad_group_id: str = "4001", keyword_type: str = "BROAD",
             keyword_id: str = "5001", keyword_text: str | None = None, clicks: int = 10, orders: int = 0,
             cost: float = 5.0, sales: float = 0.0, portfolio: str = "", portfolio_id: str = "",
             campaign_name: str | None = None, status: str = "ENABLED") -> dict:
    """One search term row as `search_terms_between` answers it."""
    match_type = keyword_type if keyword_type in ("BROAD", "PHRASE", "EXACT") else ""
    return {"campaign_id": campaign_id, "ad_group_id": ad_group_id, "keyword_type": keyword_type,
            "keyword_id": keyword_id, "match_type": match_type, "targeting": keyword_text or text,
            "search_term": text, "campaign_name": campaign_name or f"Luna - SP - {campaign_id}",
            "campaign_status": status, "ad_group_name": f"AG {ad_group_id}", "keyword_text": keyword_text or text,
            "ad_keyword_status": "ENABLED", "portfolio_id": portfolio_id, "portfolio_name": portfolio,
            "currency_code": "USD", "impressions": 500, "clicks": clicks, "purchases_7d": orders, "units_7d": orders,
            "purchases_14d": orders, "units_14d": orders, "cost": cost, "sales_7d": sales, "sales_14d": sales}


def search_terms_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SEARCH_TERM_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class _SearchTermsRest:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def rpc_csv(self, name, args, *, timeout_s=8):
        assert name == "search_terms_between"
        return search_terms_csv(self._rows)


def search_terms(*rows: dict) -> pd.DataFrame:
    """The canonical frame the provider builds from these rows, seller attribution (7 days)."""
    return ReportProvider(_SearchTermsRest(list(rows))).search_terms(PROFILE, START, END).frame


def sqp_row(query: str, *, impressions: int = 1000, clicks: int = 100, purchases: int = 10,
            brand_purchases: float | None = 1, brand_share: float | None = 10.0, brand_impressions: int = 100,
            brand_clicks: int = 10, score: int = 1, purchase_rate: float = 1.0) -> dict:
    return {"Search Query": query, "Search Query Score": score, "Impressions: Total Count": impressions,
            "Impressions: Brand Count": brand_impressions, "Clicks: Total Count": clicks,
            "Clicks: Brand Count": brand_clicks, "Purchases: Total Count": purchases,
            "Purchases: Brand Count": brand_purchases, "Purchases: Brand Share %": brand_share,
            "Purchases: Purchase Rate %": purchase_rate}


def sqp(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))

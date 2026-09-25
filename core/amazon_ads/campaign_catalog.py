"""Every campaign of an account's Sponsored Products, Brands and Display as last listed.

It is what a campaign name or id is resolved against, and where a campaign's state, portfolio and daily budget
come from when its figures come from the reports. Reads `campaign_catalog` (migration 019).
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from core.amazon_ads.report_provider import (
    READ_TIMEOUT_SECONDS,
    ReportReadError,
    _is_missing_function,
    _portfolio_label,
)
from core.integrations.store import _error_message, _Rest

log = logging.getLogger(__name__)

CATALOG_RPC = "campaign_catalog"
CATALOG_COLUMNS = ("product", "campaign_id", "campaign", "state", "portfolio", "daily_budget")
_RPC_FIELDS = ("ad_product", "campaign_id", "name", "state", "portfolio_id", "portfolio_name", "budget_amount",
               "budget_type")
_DAILY_BUDGET = "DAILY"
_ACTION = "leer las campañas de la cuenta de Amazon Ads"


def campaign_catalog(rest: _Rest, profile_id: str) -> pd.DataFrame | None:
    """One row per listed campaign in CATALOG_COLUMNS; None while the database lacks migration 019."""
    try:
        csv_bytes = rest.rpc_csv(CATALOG_RPC, {"p_profile_id": profile_id}, timeout_s=READ_TIMEOUT_SECONDS)
    except requests.HTTPError as exc:
        if _is_missing_function(exc):
            log.info("amazon ads: %s does not exist yet (migration 019 pending)", CATALOG_RPC)
            return None
        raise ReportReadError(_error_message(exc, _ACTION)) from exc
    except requests.RequestException as exc:
        raise ReportReadError(_error_message(exc, _ACTION)) from exc
    try:
        return catalog_frame(csv_bytes)
    except ValueError as exc:
        raise ReportReadError(_error_message(exc, _ACTION)) from exc


def catalog_frame(csv_bytes: bytes) -> pd.DataFrame:
    """The RPC's answer in CATALOG_COLUMNS; raises ValueError on a malformed one."""
    if not csv_bytes.strip():
        return pd.DataFrame(columns=list(CATALOG_COLUMNS))
    # keep_default_na=False: a campaign named "NA" is text, not a missing value.
    raw = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [field for field in _RPC_FIELDS if field not in raw.columns]
    if missing:
        raise ValueError(f"{CATALOG_RPC} answered without columns {missing}")
    # PostgREST writes text/csv from record_out, which doubles every backslash inside a field.
    raw = raw.apply(lambda column: column.str.replace("\\\\", "\\", regex=False))
    budget = pd.to_numeric(raw["budget_amount"].str.strip(), errors="coerce")
    daily = raw["budget_type"].str.strip().str.upper().eq(_DAILY_BUDGET)
    return pd.DataFrame({
        "product": raw["ad_product"],
        "campaign_id": raw["campaign_id"],
        "campaign": raw["name"].str.strip(),
        "state": raw["state"].str.strip().str.upper(),
        "portfolio": [_portfolio_label(portfolio_id, name) for portfolio_id, name
                      in zip(raw["portfolio_id"], raw["portfolio_name"])],
        "daily_budget": budget.where(daily),
    }, columns=list(CATALOG_COLUMNS))

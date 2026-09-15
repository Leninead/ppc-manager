"""Sponsored Products portfolio names per profile, for labelling search terms."""
from __future__ import annotations

import logging
from datetime import datetime

from core.amazon_ads.api_client import AdsApiClient, AdsApiError
from core.integrations.store import _Rest

log = logging.getLogger(__name__)

PORTFOLIO_CONTENT_TYPE = "application/vnd.spPortfolio.v3+json"
PORTFOLIOS_LIST_PATH = "/portfolios/list"
PORTFOLIOS_TABLE = "ads_portfolios"
# A profile with more pages than this means the paging token is looping, not real portfolios.
MAX_PAGES = 200


def fetch_portfolios(api: AdsApiClient, profile_id: str) -> list[dict]:
    portfolios: list[dict] = []
    seen_tokens: set[str] = set()
    request_body: dict = {}
    for _ in range(MAX_PAGES):
        response = api.request(
            "POST",
            PORTFOLIOS_LIST_PATH,
            profile_id=profile_id,
            json_body=request_body,
            content_type=PORTFOLIO_CONTENT_TYPE,
        )
        try:
            page = response.json()
        except ValueError:
            raise AdsApiError(f"unreadable portfolios page for profile {profile_id}",
                              status=response.status_code) from None
        if not isinstance(page, dict):
            raise AdsApiError(f"unexpected portfolios page for profile {profile_id}", status=response.status_code)
        portfolios.extend(_portfolio_row(raw) for raw in page.get("portfolios") or [] if _has_id(raw))

        next_token = str(page.get("nextToken") or "")
        if not next_token:
            return portfolios
        if next_token in seen_tokens:
            log.warning("amazon_ads: profile %s repeated a portfolios page token, stopping", profile_id)
            return portfolios
        seen_tokens.add(next_token)
        request_body = {"nextToken": next_token}
    raise AdsApiError(f"portfolios for profile {profile_id} exceeded {MAX_PAGES} pages")


def save_portfolios(rest: _Rest, profile_id: str, portfolios: list[dict], seen_at: datetime) -> int:
    """Upsert only: an archived portfolio can drop out of the listing, and its name must survive."""
    rows_by_id = {
        portfolio["portfolio_id"]: {
            "profile_id": profile_id,
            "portfolio_id": portfolio["portfolio_id"],
            "name": portfolio.get("name") or "",
            "state": portfolio.get("state") or "",
            "seen_at": seen_at.isoformat(),
        }
        for portfolio in portfolios
        if portfolio.get("portfolio_id")
    }
    if not rows_by_id:
        return 0
    # PostgREST takes an array body as one bulk upsert; duplicates in one batch would fail it, hence the dict.
    rest.upsert(PORTFOLIOS_TABLE, list(rows_by_id.values()), on_conflict="profile_id,portfolio_id")
    return len(rows_by_id)


def _has_id(raw) -> bool:
    return isinstance(raw, dict) and raw.get("portfolioId") not in (None, "")


def _portfolio_row(raw: dict) -> dict:
    return {
        "portfolio_id": str(raw["portfolioId"]).strip(),
        "name": str(raw.get("name") or ""),
        "state": str(raw.get("state") or ""),
    }

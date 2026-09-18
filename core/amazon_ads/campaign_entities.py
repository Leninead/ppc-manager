"""Sponsored Products campaign entities per profile, mapped to `ads_campaign`.

This is the campaign universe: every campaign the profile has, including the ones with no
activity. The spCampaigns report only returns campaigns that had activity in the range asked
for, so the metrics alone would silently lose the quiet ones.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from core.amazon_ads.api_client import AdsApiClient, AdsApiError
from core.integrations.store import _Rest

log = logging.getLogger(__name__)

CAMPAIGN_CONTENT_TYPE = "application/vnd.spCampaign.v3+json"
CAMPAIGNS_LIST_PATH = "/sp/campaigns/list"
CAMPAIGNS_TABLE = "ads_campaign"
# A profile with more pages than this means the paging token is looping, not real campaigns.
MAX_PAGES = 200


def fetch_campaigns(api: AdsApiClient, profile_id: str) -> list[dict]:
    campaigns: list[dict] = []
    seen_tokens: set[str] = set()
    request_body: dict = {}
    for _ in range(MAX_PAGES):
        response = api.request(
            "POST",
            CAMPAIGNS_LIST_PATH,
            profile_id=profile_id,
            json_body=request_body,
            content_type=CAMPAIGN_CONTENT_TYPE,
            # Without Accept this endpoint answers 415 to the session's default `*/*`.
            accept=CAMPAIGN_CONTENT_TYPE,
        )
        try:
            page = response.json()
        except ValueError:
            raise AdsApiError(f"unreadable campaigns page for profile {profile_id}",
                              status=response.status_code) from None
        if not isinstance(page, dict):
            raise AdsApiError(f"unexpected campaigns page for profile {profile_id}",
                              status=response.status_code)
        campaigns.extend(_campaign_row(raw) for raw in page.get("campaigns") or [] if _has_id(raw))

        next_token = str(page.get("nextToken") or "")
        if not next_token:
            return campaigns
        if next_token in seen_tokens:
            log.warning("amazon_ads: profile %s repeated a campaigns page token, stopping", profile_id)
            return campaigns
        seen_tokens.add(next_token)
        request_body = {"nextToken": next_token}
    raise AdsApiError(f"campaigns for profile {profile_id} exceeded {MAX_PAGES} pages")


def save_campaigns(rest: _Rest, profile_id: str, campaigns: list[dict], seen_at: datetime) -> int:
    """Upsert only: a campaign can drop out of the listing, and M6 still needs its name and state."""
    rows_by_id = {
        campaign["campaign_id"]: {**campaign, "profile_id": profile_id, "seen_at": seen_at.isoformat()}
        for campaign in campaigns
        if campaign.get("campaign_id")
    }
    if not rows_by_id:
        return 0
    # PostgREST takes an array body as one bulk upsert; duplicates in one batch would fail it, hence the dict.
    rest.upsert(CAMPAIGNS_TABLE, list(rows_by_id.values()), on_conflict="profile_id,campaign_id")
    return len(rows_by_id)


def _has_id(raw) -> bool:
    return isinstance(raw, dict) and raw.get("campaignId") not in (None, "")


def _campaign_row(raw: dict) -> dict:
    budget = raw.get("budget") if isinstance(raw.get("budget"), dict) else {}
    bidding = raw.get("dynamicBidding") if isinstance(raw.get("dynamicBidding"), dict) else {}
    return {
        "campaign_id": _id_text(raw["campaignId"]),
        "name": str(raw.get("name") or ""),
        "state": str(raw.get("state") or ""),
        "targeting_type": str(raw.get("targetingType") or ""),
        "start_date": _day(raw.get("startDate")),
        "end_date": _day(raw.get("endDate")),
        "budget_amount": _amount(budget.get("budget")),
        "budget_type": str(budget.get("budgetType") or ""),
        "bidding_strategy": str(bidding.get("strategy") or ""),
        # Amazon omits portfolioId entirely when the campaign is in no portfolio.
        "portfolio_id": _id_text(raw.get("portfolioId")),
    }


def _id_text(value) -> str:
    # Amazon sends ids as JSON numbers; a float rendering ("1.5e+14") would break every join.
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _day(value) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        log.warning("amazon_ads: campaign date %r is not a date, stored empty", raw)
        return None


def _amount(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        log.warning("amazon_ads: campaign budget %r is not a number, stored empty", value)
        return None

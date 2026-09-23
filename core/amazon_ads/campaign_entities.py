"""Sponsored Products campaign entities per profile, mapped to `ads_campaign`.

This is the campaign universe: every campaign the profile has, including the ones with no
activity. The spCampaigns report only returns campaigns that had activity in the range asked
for, so the metrics alone would silently lose the quiet ones. The same listing carries each
campaign's bid adjustment per placement.
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
# Amazon's placement names and the `ads_campaign` column that keeps each one's percentage.
PLACEMENT_COLUMNS = {
    "PLACEMENT_TOP": "placement_top_pct",
    "PLACEMENT_PRODUCT_PAGE": "placement_product_page_pct",
    "PLACEMENT_REST_OF_SEARCH": "placement_rest_of_search_pct",
    "SITE_AMAZON_BUSINESS": "amazon_business_pct",
}


def fetch_campaigns(api: AdsApiClient, profile_id: str) -> list[dict]:
    listed = _list_campaigns(api, profile_id)
    unknown_placements = sorted({_placement_name(adjustment) for raw in listed
                                 for adjustment in _placement_adjustments(raw)} - PLACEMENT_COLUMNS.keys())
    if unknown_placements:
        log.warning("amazon_ads: profile %s lists placements %s, which have no column and are not stored",
                    profile_id, ", ".join(unknown_placements))
    return [_campaign_row(raw) for raw in listed]


def _list_campaigns(api: AdsApiClient, profile_id: str) -> list[dict]:
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
        campaigns.extend(raw for raw in page.get("campaigns") or [] if _has_id(raw))

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
        **_placement_percentages(raw),
    }


def _placement_percentages(raw: dict) -> dict[str, int | None]:
    """Every placement column on every row, as the bulk upsert needs: 0 where the listed campaign has no
    adjustment, None (unknown) when Amazon sent no dynamicBidding at all."""
    if not isinstance(raw.get("dynamicBidding"), dict):
        return dict.fromkeys(PLACEMENT_COLUMNS.values())
    percentages: dict[str, int | None] = dict.fromkeys(PLACEMENT_COLUMNS.values(), 0)
    for adjustment in _placement_adjustments(raw):
        column = PLACEMENT_COLUMNS.get(_placement_name(adjustment))
        if column is not None:
            percentages[column] = _percentage(adjustment.get("percentage"))
    return percentages


def _placement_adjustments(raw: dict) -> list[dict]:
    bidding = raw.get("dynamicBidding")
    adjustments = bidding.get("placementBidding") if isinstance(bidding, dict) else None
    return [item for item in adjustments if isinstance(item, dict)] if isinstance(adjustments, list) else []


def _placement_name(adjustment: dict) -> str:
    return str(adjustment.get("placement") or "")


def _percentage(value) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = None
    if number is None or not number.is_integer():
        log.warning("amazon_ads: placement percentage %r is not a whole number, stored empty", value)
        return None
    return int(number)


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

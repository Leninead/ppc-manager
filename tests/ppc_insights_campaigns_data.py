"""Synthetic SP listings for the PPC Insights campaign tests.

The rows go through the real StructureProvider, so every test reads what `sp_structure_between` answers the page.
"""
import csv
import io
from datetime import date, datetime, timezone

import requests

from core.amazon_ads.report_provider import ProfileOption
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    CAMPAIGN,
    KEYWORD,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    ROW_COLUMNS,
)
from core.ppc_insights.campaign_coverage import ListedCampaigns, read_campaign_listing

LISTED_AT = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
DAY = date(2026, 9, 28)
PROFILE = ProfileOption.from_row({"profile_id": "111", "cliente": "Luna Kids", "country_code": "US",
                                  "currency_code": "USD", "account_type": "seller", "status": "active"})


def _row(entity, campaign_id, entity_id, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "campaign_id": campaign_id, "entity_id": entity_id,
                "campaign_name": f"Luna - SP - {campaign_id}", "state": "ENABLED", "metrics_known": "f",
                "currency_code": "USD", "listed_at": LISTED_AT.isoformat()})
    row.update(values)
    return row


def campaign(campaign_id, name, *, targeting="MANUAL", state="ENABLED") -> dict:
    return _row(CAMPAIGN, campaign_id, campaign_id, campaign_name=name, targeting_type=targeting, state=state)


def ad_group(campaign_id, ad_group_id, *, state="ENABLED") -> dict:
    return _row(AD_GROUP, campaign_id, ad_group_id, ad_group_id=ad_group_id, state=state)


def product_ad(campaign_id, ad_group_id, asin, *, state="ENABLED") -> dict:
    return _row(PRODUCT_AD, campaign_id, f"ad-{ad_group_id}-{asin}", ad_group_id=ad_group_id, asin=asin, state=state)


def keyword(campaign_id, ad_group_id, text, match_type, *, state="ENABLED") -> dict:
    return _row(KEYWORD, campaign_id, f"kw-{ad_group_id}-{text}-{match_type}", ad_group_id=ad_group_id,
                target_kind="keyword", target_text=text, match_type=match_type, state=state)


def product_target(campaign_id, ad_group_id, expression, *, state="ENABLED") -> dict:
    return _row(PRODUCT_TARGETING, campaign_id, f"pt-{ad_group_id}-{expression}", ad_group_id=ad_group_id,
                target_kind="product", target_text=expression, state=state)


def completed_job(kind, *, warning="") -> dict:
    return {"id": 9, "integration_slug": "amazon_ads", "job_kind": kind, "trigger": "scheduled_daily",
            "external_account_id": "111", "status": "completed", "warning": warning,
            "finished_at": LISTED_AT.isoformat(), "created_at": LISTED_AT.isoformat()}


class ListingRest:
    """sp_structure_between over these rows, and the completed listing jobs, as PostgREST answers them."""

    def __init__(self, rows=(), *, jobs=(), missing=False, fail=False):
        self._rows, self._jobs, self._missing, self._fail = list(rows), list(jobs), missing, fail
        self.reads: list[dict] = []

    def rpc_csv(self, name, args, *, timeout_s=8):
        assert name == "sp_structure_between"
        self.reads.append(args)
        if self._fail:
            raise requests.ConnectionError("gateway down")
        if self._missing:
            response = requests.Response()
            response.status_code = 404
            response._content = b'{"code":"PGRST202","message":"Could not find the function"}'
            raise requests.HTTPError(response=response)
        entities = set(args.get("p_entities") or ())
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(ROW_COLUMNS))
        writer.writeheader()
        writer.writerows(row for row in self._rows if not entities or row["entity"] in entities)
        return buffer.getvalue().encode("utf-8")

    def select(self, table, params):
        assert table == "integration_sync_jobs", table
        kind = params.get("job_kind", "").removeprefix("eq.")
        return [dict(job) for job in self._jobs if job["job_kind"] == kind][:1]


def listed_campaigns(*rows) -> ListedCampaigns:
    """The coverage the page reads from a listing with these rows."""
    listing = read_campaign_listing(ListingRest(rows), PROFILE, DAY)
    assert listing.campaigns is not None, listing.missing_reason
    return listing.campaigns

"""Campaign entities: paginated v3 listing, the Accept header it needs, placements, and upsert-only persistence."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from core.amazon_ads.api_client import AdsApiClient, AdsApiError
from core.amazon_ads.campaign_entities import (
    CAMPAIGN_CONTENT_TYPE,
    CAMPAIGNS_TABLE,
    PLACEMENT_COLUMNS,
    fetch_campaigns,
    save_campaigns,
)

PLACEMENT_KEYS = ("placement_top_pct", "placement_product_page_pct", "placement_rest_of_search_pct",
                  "amazon_business_pct")


class _FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self.headers = {}
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class _FakeSession:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": json})
        return self._outcomes.pop(0)


class _FakeRest:
    def __init__(self):
        self.upserts = []

    def upsert(self, table, row, on_conflict=None):
        self.upserts.append((table, row, on_conflict))

    def delete(self, *args, **kwargs):
        raise AssertionError("campaign entities are never deleted")


def _api(outcomes):
    session = _FakeSession(outcomes)
    client = AdsApiClient(region="NA", client_id="client-abc", token_source=lambda force: "token",
                          session=session, sleep=lambda seconds: None)
    return client, session


def _campaign(campaign_id, name="Demo - SP - KW - EXACT", **overrides):
    campaign = {
        "campaignId": campaign_id,
        "name": name,
        "state": "ENABLED",
        "targetingType": "MANUAL",
        "startDate": "2026-03-21",
        "budget": {"budget": 15.0, "budgetType": "DAILY"},
        "dynamicBidding": {"strategy": "MANUAL", "placementBidding": []},
        "portfolioId": "777",
    }
    campaign.update(overrides)
    return campaign


def test_fetch_sends_the_accept_header_the_endpoint_demands():
    api, session = _api([_FakeResponse(200, {"campaigns": [_campaign("101")]})])

    fetch_campaigns(api, "555")

    assert session.calls[0]["headers"]["Accept"] == CAMPAIGN_CONTENT_TYPE
    assert session.calls[0]["headers"]["Content-Type"] == CAMPAIGN_CONTENT_TYPE


def test_fetch_follows_next_token_until_the_last_page():
    api, _ = _api([
        _FakeResponse(200, {"campaigns": [_campaign("101", "Brand")], "nextToken": "page-2"}),
        _FakeResponse(200, {"campaigns": [_campaign(102, "Generic")]}),
    ])

    campaigns = fetch_campaigns(api, "555")

    assert [campaign["campaign_id"] for campaign in campaigns] == ["101", "102"]


def test_fetch_stops_when_a_page_token_repeats():
    api, session = _api([
        _FakeResponse(200, {"campaigns": [_campaign("101")], "nextToken": "loop"}),
        _FakeResponse(200, {"campaigns": [_campaign("102")], "nextToken": "loop"}),
    ])

    campaigns = fetch_campaigns(api, "555")

    assert [campaign["campaign_id"] for campaign in campaigns] == ["101", "102"]
    assert len(session.calls) == 2


def test_budget_and_bidding_come_out_of_their_nested_objects():
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign("101")]})])

    campaign = fetch_campaigns(api, "555")[0]

    assert campaign["budget_amount"] == 15.0
    assert campaign["budget_type"] == "DAILY"
    assert campaign["bidding_strategy"] == "MANUAL"
    assert campaign["targeting_type"] == "MANUAL"
    assert campaign["start_date"] == "2026-03-21"


def test_a_campaign_in_no_portfolio_comes_back_with_an_empty_portfolio_id():
    # Amazon omits the key entirely rather than sending null.
    raw = _campaign("101")
    raw.pop("portfolioId")
    api, _ = _api([_FakeResponse(200, {"campaigns": [raw]})])

    assert fetch_campaigns(api, "555")[0]["portfolio_id"] == ""


def test_numeric_campaign_ids_never_come_out_in_float_notation():
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign(218190823249654.0)]})])

    assert fetch_campaigns(api, "555")[0]["campaign_id"] == "218190823249654"


def test_a_missing_budget_object_leaves_the_amount_empty_instead_of_zero():
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign("101", budget=None)]})])

    campaign = fetch_campaigns(api, "555")[0]

    assert campaign["budget_amount"] is None
    assert campaign["budget_type"] == ""


def _placements(campaign: dict) -> tuple:
    return tuple(campaign[key] for key in PLACEMENT_KEYS)


def _bidding(*adjustments) -> dict:
    return {"strategy": "AUTO_FOR_SALES",
            "placementBidding": [{"placement": placement, "percentage": percentage}
                                 for placement, percentage in adjustments]}


def test_the_four_placements_map_to_their_own_columns():
    assert set(PLACEMENT_COLUMNS.values()) == set(PLACEMENT_KEYS)
    bidding = _bidding(("PLACEMENT_TOP", 50), ("PLACEMENT_PRODUCT_PAGE", 25), ("PLACEMENT_REST_OF_SEARCH", 10),
                       ("SITE_AMAZON_BUSINESS", 900))
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign("101", dynamicBidding=bidding)]})])

    assert _placements(fetch_campaigns(api, "555")[0]) == (50, 25, 10, 900)


def test_a_placement_without_an_adjustment_is_zero_not_unknown():
    top_only = _campaign("101", dynamicBidding=_bidding(("PLACEMENT_TOP", 35)))
    api, _ = _api([_FakeResponse(200, {"campaigns": [top_only]})])

    assert _placements(fetch_campaigns(api, "555")[0]) == (35, 0, 0, 0)


@pytest.mark.parametrize("bidding", [
    pytest.param({"strategy": "MANUAL", "placementBidding": []}, id="empty-list"),
    pytest.param({"strategy": "MANUAL"}, id="missing-key"),
])
def test_a_listed_campaign_without_adjustments_has_every_placement_at_zero(bidding):
    # Whether Amazon omits placementBidding or sends [] is not verified yet; both mean no adjustment.
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign("101", dynamicBidding=bidding)]})])

    assert _placements(fetch_campaigns(api, "555")[0]) == (0, 0, 0, 0)


@pytest.mark.parametrize("bidding", [pytest.param(None, id="null"), pytest.param("MANUAL", id="not-an-object")])
def test_without_dynamic_bidding_every_placement_is_unknown(bidding):
    raw = _campaign("101", dynamicBidding=bidding)
    missing = _campaign("102")
    missing.pop("dynamicBidding")
    api, _ = _api([_FakeResponse(200, {"campaigns": [raw, missing]})])

    campaigns = fetch_campaigns(api, "555")

    assert [_placements(campaign) for campaign in campaigns] == [(None, None, None, None)] * 2
    assert [campaign["bidding_strategy"] for campaign in campaigns] == ["", ""]


@pytest.mark.parametrize("percentage", [12.5, "half", None])
def test_a_percentage_that_is_not_a_whole_number_is_stored_empty_with_a_warning(percentage, caplog):
    bidding = _bidding(("PLACEMENT_TOP", percentage), ("PLACEMENT_PRODUCT_PAGE", 40.0))
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign("101", dynamicBidding=bidding)]})])

    with caplog.at_level(logging.WARNING, logger="core.amazon_ads.campaign_entities"):
        campaign = fetch_campaigns(api, "555")[0]

    assert _placements(campaign) == (None, 40, 0, 0)
    assert any("placement percentage" in record.getMessage() for record in caplog.records)


def test_an_unknown_placement_is_logged_once_per_listing_and_never_stored(caplog):
    unknown = _bidding(("PLACEMENT_TOP", 20), ("PLACEMENT_HOME_PAGE", 30))
    api, _ = _api([
        _FakeResponse(200, {"campaigns": [_campaign("101", dynamicBidding=unknown)], "nextToken": "page-2"}),
        _FakeResponse(200, {"campaigns": [_campaign("102", dynamicBidding=unknown),
                                          _campaign("103", dynamicBidding=_bidding(("PLACEMENT_OFF_SITE", 5)))]}),
    ])

    with caplog.at_level(logging.WARNING, logger="core.amazon_ads.campaign_entities"):
        campaigns = fetch_campaigns(api, "555")

    [warning] = [record.getMessage() for record in caplog.records]
    assert "PLACEMENT_HOME_PAGE, PLACEMENT_OFF_SITE" in warning and "555" in warning
    assert [_placements(campaign) for campaign in campaigns] == [(20, 0, 0, 0), (20, 0, 0, 0), (0, 0, 0, 0)]
    assert all("PLACEMENT_HOME_PAGE" not in str(campaign) for campaign in campaigns)


def test_every_campaign_row_carries_the_four_placement_columns():
    # PostgREST takes a bulk upsert only when every object in it has the same keys.
    bare = {"campaignId": "103"}
    api, _ = _api([_FakeResponse(200, {"campaigns": [
        _campaign("101", dynamicBidding=_bidding(("PLACEMENT_TOP", 50))), _campaign("102"), bare]})])

    campaigns = fetch_campaigns(api, "555")

    assert len({frozenset(campaign) for campaign in campaigns}) == 1
    assert set(PLACEMENT_KEYS) <= set(campaigns[0])


def test_an_unparseable_start_date_is_stored_empty_rather_than_guessed():
    api, _ = _api([_FakeResponse(200, {"campaigns": [_campaign("101", startDate="not-a-date")]})])

    assert fetch_campaigns(api, "555")[0]["start_date"] is None


def test_a_page_that_is_not_json_is_refused():
    class _Unreadable(_FakeResponse):
        def json(self):
            raise ValueError("not json")

    api, _ = _api([_Unreadable(200)])

    with pytest.raises(AdsApiError):
        fetch_campaigns(api, "555")


def test_save_upserts_one_row_per_campaign_with_the_profile_and_timestamp():
    rest = _FakeRest()
    seen_at = datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)

    written = save_campaigns(rest, "555", [
        {"campaign_id": "101", "name": "Brand", "state": "ENABLED"},
        {"campaign_id": "102", "name": "Generic", "state": "PAUSED"},
    ], seen_at)

    table, rows, on_conflict = rest.upserts[0]
    assert (written, table, on_conflict) == (2, CAMPAIGNS_TABLE, "profile_id,campaign_id")
    assert rows[0]["profile_id"] == "555"
    assert rows[0]["seen_at"] == seen_at.isoformat()


def test_save_keeps_one_row_per_campaign_id_so_the_bulk_upsert_is_accepted():
    rest = _FakeRest()

    written = save_campaigns(rest, "555", [
        {"campaign_id": "101", "name": "First"},
        {"campaign_id": "101", "name": "Second"},
    ], datetime(2026, 9, 17, tzinfo=timezone.utc))

    _, rows, _ = rest.upserts[0]
    assert written == 1
    assert rows[0]["name"] == "Second"


def test_save_writes_nothing_when_there_is_nothing_to_write():
    rest = _FakeRest()

    assert save_campaigns(rest, "555", [], datetime(2026, 9, 17, tzinfo=timezone.utc)) == 0
    assert rest.upserts == []

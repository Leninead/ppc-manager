"""SP/SB/SD targets, SB/SD campaigns and SP product ads, ad groups and negatives: the verified listing contracts,
paging, row mapping and batched saves."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from typing import NamedTuple

import pytest

from core.amazon_ads import ad_entities
from core.amazon_ads.ad_entities import (
    AD_GROUPS_TABLE,
    LISTING_SNAPSHOTS_TABLE,
    NEGATIVES_TABLE,
    PRODUCT_ADS_TABLE,
    PRODUCT_CAMPAIGNS_TABLE,
    SP_NEGATIVE_LISTINGS,
    TARGETS_TABLE,
    NegativePage,
    fetch_negative_page,
    fetch_sb_campaigns,
    fetch_sb_targets,
    fetch_sd_campaigns,
    fetch_sd_targets,
    fetch_sp_ad_groups,
    fetch_sp_product_ads,
    fetch_sp_targets,
    save_ad_groups,
    save_listing_snapshot,
    save_negatives,
    save_product_ads,
    save_product_campaigns,
    save_targets,
)
from core.amazon_ads.api_client import AdsAccessDenied, AdsApiClient, AdsApiError, AdsThrottled

HOST = "https://advertising-api.amazon.com"
SEEN_AT = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
TARGET_COLUMNS = {"ad_product", "target_id", "campaign_id", "ad_group_id", "target_kind", "target_text",
                  "match_type", "state", "bid"}
NEGATIVE_COLUMNS = {"negative_id", "level", "negative_kind", "campaign_id", "ad_group_id", "negative_text",
                    "match_type", "state"}
# The four SP negative listings, in the order of SP_NEGATIVE_LISTINGS.
NEGATIVE_PATHS = ["/sp/negativeKeywords/list", "/sp/campaignNegativeKeywords/list", "/sp/negativeTargets/list",
                  "/sp/campaignNegativeTargets/list"]
# What each listing answers for a profile with nothing in it.
EMPTY_PAGES = {
    "/sp/keywords/list": {"keywords": []},
    "/sp/targets/list": {"targetingClauses": []},
    "/sp/productAds/list": {"productAds": []},
    "/sp/adGroups/list": {"adGroups": []},
    "/sp/negativeKeywords/list": {"negativeKeywords": []},
    "/sp/campaignNegativeKeywords/list": {"campaignNegativeKeywords": []},
    "/sp/negativeTargets/list": {"negativeTargetingClauses": []},
    "/sp/campaignNegativeTargets/list": {"campaignNegativeTargetingClauses": []},
    "/sb/v4/campaigns/list": {"campaigns": []},
    "/sb/keywords": [],
    "/sb/targets/list": {"targets": []},
    "/sb/themes/list": {"themes": []},
    "/sd/campaigns": [],
    "/sd/adGroups": [],
    "/sd/targets": [],
}


class _FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self.headers = {}
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class _Unreadable(_FakeResponse):
    def json(self):
        raise ValueError("not json")


class _FakeSession:
    """Answers each listing from its own queue, so a fetcher reading several needs no call order."""

    def __init__(self, pages_by_path):
        self._queues = {path: list(pages) for path, pages in pages_by_path.items()}
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": json})
        path = _path(url)
        if path not in self._queues:
            return _FakeResponse(200, EMPTY_PAGES[path])
        queue = self._queues[path]
        assert queue, f"unexpected extra call to {path}"
        page = queue.pop(0)
        return page if isinstance(page, _FakeResponse) else _FakeResponse(200, page)

    def calls_to(self, path):
        return [call for call in self.calls if _path(call["url"]) == path]


class _FakeRest:
    def __init__(self):
        self.upserts = []

    def upsert(self, table, row, on_conflict=None):
        self.upserts.append((table, row, on_conflict))

    def delete(self, *args, **kwargs):
        raise AssertionError("ad entities are never deleted")


def _path(url):
    return url.removeprefix(HOST).split("?")[0]


def _api(pages_by_path=None):
    session = _FakeSession(pages_by_path or {})
    client = AdsApiClient(region="NA", client_id="client-abc", token_source=lambda force: "token",
                          session=session, sleep=lambda seconds: None)
    return client, session


def _ids(rows):
    return [row.get("target_id") or row.get("ad_id") or row.get("negative_id") or row.get("ad_group_id")
            or row.get("campaign_id") for row in rows]


def _sp_product_ad(ad_id=17, **overrides):
    return {"adId": str(ad_id), "adGroupId": "21", "campaignId": "31", "asin": "b0demo0004", "sku": " DEMO-SKU ",
            "state": "ENABLED", **overrides}


def _sp_ad_group(ad_group_id=21, **overrides):
    return {"adGroupId": str(ad_group_id), "campaignId": "31", "name": "Demo - Exact", "state": "ENABLED",
            "defaultBid": 0.75, **overrides}


def _sp_negative_keyword(keyword_id=81, **overrides):
    return {"keywordId": str(keyword_id), "adGroupId": "21", "campaignId": "31", "keywordText": "free demo",
            "matchType": "NEGATIVE_EXACT", "state": "ENABLED", **overrides}


def _sp_campaign_negative_keyword(keyword_id=82, **overrides):
    # Campaign-level negatives belong to no ad group: Amazon sends no adGroupId for them.
    return {"keywordId": str(keyword_id), "campaignId": "31", "keywordText": "cheap demo",
            "matchType": "NEGATIVE_PHRASE", "state": "ENABLED", **overrides}


def _sp_negative_target(target_id=83, predicates=None, **overrides):
    predicates = predicates if predicates is not None else [{"type": "ASIN_SAME_AS", "value": "B0RIVAL001"}]
    return {"targetId": str(target_id), "adGroupId": "21", "campaignId": "31", "expression": predicates,
            "resolvedExpression": predicates, "state": "ENABLED", **overrides}


def _sp_campaign_negative_target(target_id=84, predicates=None, **overrides):
    predicates = predicates if predicates is not None else [{"type": "ASIN_BRAND_SAME_AS", "value": "Rival Brand"}]
    return {"targetId": str(target_id), "campaignId": "31", "expression": predicates,
            "resolvedExpression": predicates, "state": "ENABLED", **overrides}


def _sp_keyword(keyword_id=11, **overrides):
    return {"keywordId": str(keyword_id), "adGroupId": "21", "campaignId": "31", "keywordText": "demo shorts",
            "matchType": "EXACT", "state": "ENABLED", "bid": 1.25, **overrides}


def _sp_clause(target_id=12, predicates=None, expression_type="MANUAL", **overrides):
    predicates = predicates if predicates is not None else [{"type": "ASIN_SAME_AS", "value": "B0DEMO0001"}]
    return {"targetId": str(target_id), "adGroupId": "21", "campaignId": "31", "bid": 0.8,
            "expression": predicates, "expressionType": expression_type, "resolvedExpression": predicates,
            "state": "PAUSED", **overrides}


def _sb_campaign(campaign_id=41, **overrides):
    return {"campaignId": str(campaign_id), "name": "Demo - SBV - KW", "state": "ENABLED", "budget": 5.0,
            "budgetType": "DAILY", "costType": "CPC", "goal": "PAGE_VISIT", "isMultiAdGroupsEnabled": False,
            "portfolioId": "51", "startDate": "2026-03-05", "kpi": "CLICKS",
            "bidding": {"bidOptimization": True}, **overrides}


def _sb_keyword(keyword_id=13, **overrides):
    return {"keywordId": keyword_id, "adGroupId": 22, "campaignId": 32, "keywordText": "demo bra",
            "matchType": "phrase", "state": "enabled", "bid": 2.5, **overrides}


def _sb_target(target_id=14, predicates=None, **overrides):
    predicates = predicates if predicates is not None else [{"type": "asinSameAs", "value": "B0DEMO0002"}]
    return {"targetId": target_id, "adGroupId": 22, "campaignId": 32, "state": "enabled", "bid": 1.5,
            "expressions": predicates, "resolvedExpressions": predicates, **overrides}


def _sb_theme(theme_id=15, **overrides):
    return {"themeId": str(theme_id), "adGroupId": "22", "campaignId": "32",
            "themeType": "KEYWORDS_RELATED_TO_YOUR_BRAND", "state": "enabled", "bid": 3.0, **overrides}


def _sd_campaign(campaign_id=61, **overrides):
    return {"campaignId": campaign_id, "portfolioId": 52, "name": "Demo - SD - Products", "tactic": "T00020",
            "startDate": "20201020", "state": "enabled", "costType": "cpc", "budget": 15.0,
            "budgetType": "daily", "deliveryProfile": "as_soon_as_possible", **overrides}


def _sd_target(target_id=16, predicates=None, expression_type="manual", **overrides):
    predicates = predicates if predicates is not None else [{"type": "asinSameAs", "value": "B0DEMO0003"}]
    return {"targetId": target_id, "adGroupId": 23, "campaignId": 33, "bid": 1.0, "expression": predicates,
            "expressionType": expression_type, "resolvedExpression": predicates, "state": "enabled",
            **overrides}


class _Listing(NamedTuple):
    fetcher: Callable
    path: str
    items_key: str | None
    factory: Callable


TOKEN_LISTINGS = [
    _Listing(fetch_sp_product_ads, "/sp/productAds/list", "productAds", _sp_product_ad),
    _Listing(fetch_sp_targets, "/sp/keywords/list", "keywords", _sp_keyword),
    _Listing(fetch_sp_targets, "/sp/targets/list", "targetingClauses", _sp_clause),
    _Listing(fetch_sp_ad_groups, "/sp/adGroups/list", "adGroups", _sp_ad_group),
    _Listing(fetch_sb_campaigns, "/sb/v4/campaigns/list", "campaigns", _sb_campaign),
    _Listing(fetch_sb_targets, "/sb/targets/list", "targets", _sb_target),
    _Listing(fetch_sb_targets, "/sb/themes/list", "themes", _sb_theme),
]
OFFSET_LISTINGS = [
    _Listing(fetch_sb_targets, "/sb/keywords", None, _sb_keyword),
    _Listing(fetch_sd_campaigns, "/sd/campaigns", None, _sd_campaign),
    _Listing(fetch_sd_targets, "/sd/targets", None, _sd_target),
]


def _by_path(listing):
    return listing.path


@pytest.mark.parametrize("fetcher, path, media_type, body", [
    pytest.param(fetch_sp_product_ads, "/sp/productAds/list", "application/vnd.spProductAd.v3+json",
                 {"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 1000}, id="sp-product-ads"),
    pytest.param(fetch_sp_targets, "/sp/keywords/list", "application/vnd.spKeyword.v3+json",
                 {"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 1000}, id="sp-keywords"),
    pytest.param(fetch_sp_targets, "/sp/targets/list", "application/vnd.spTargetingClause.v3+json",
                 {"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 1000}, id="sp-targets"),
    pytest.param(fetch_sp_ad_groups, "/sp/adGroups/list", "application/vnd.spAdGroup.v3+json",
                 {"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 1000}, id="sp-ad-groups"),
    pytest.param(fetch_sb_campaigns, "/sb/v4/campaigns/list", "application/vnd.sbcampaignresource.v4+json",
                 {"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 100}, id="sb-campaigns"),
    # Plain JSON, and no state filter: this endpoint answers 422 to one.
    pytest.param(fetch_sb_targets, "/sb/targets/list", None, {"maxResults": 1000}, id="sb-targets"),
    pytest.param(fetch_sb_targets, "/sb/themes/list", None, {"maxResults": 100}, id="sb-themes"),
])
def test_token_listings_send_the_verified_request(fetcher, path, media_type, body):
    api, session = _api()

    fetcher(api, "555")

    [call] = session.calls_to(path)
    assert (call["method"], call["url"], call["json"]) == ("POST", HOST + path, body)
    # A vendor type goes as Accept too; a plain-JSON listing gets neither header from us (requests adds
    # application/json for the body on its own).
    assert call["headers"].get("Content-Type") == media_type
    assert call["headers"].get("Accept") == media_type
    assert call["headers"]["Amazon-Advertising-API-Scope"] == "555"


@pytest.mark.parametrize("listing", OFFSET_LISTINGS, ids=_by_path)
def test_offset_listings_send_the_verified_query(listing):
    api, session = _api()

    listing.fetcher(api, "555")

    [call] = session.calls_to(listing.path)
    assert (call["method"], call["url"], call["json"]) == (
        "GET", f"{HOST}{listing.path}?startIndex=0&count=5000&stateFilter=enabled,paused", None)
    assert "Content-Type" not in call["headers"]
    assert "Accept" not in call["headers"]


@pytest.mark.parametrize("listing", TOKEN_LISTINGS, ids=_by_path)
def test_token_listings_follow_next_token_with_the_same_filters(listing):
    api, session = _api({listing.path: [
        {listing.items_key: [listing.factory(1)], "nextToken": "page-2"},
        {listing.items_key: [listing.factory(2)]},
    ]})

    rows = listing.fetcher(api, "555")

    first, second = session.calls_to(listing.path)
    assert second["json"] == {**first["json"], "nextToken": "page-2"}
    assert _ids(rows) == ["1", "2"]


def test_a_token_listing_stops_when_a_page_token_repeats():
    api, session = _api({"/sp/targets/list": [
        {"targetingClauses": [_sp_clause(1)], "nextToken": "loop"},
        {"targetingClauses": [_sp_clause(2)], "nextToken": "loop"},
    ]})

    rows = fetch_sp_targets(api, "555")

    assert _ids(rows) == ["1", "2"]
    assert len(session.calls_to("/sp/targets/list")) == 2


def test_a_token_listing_that_never_ends_is_cut_off(monkeypatch):
    monkeypatch.setattr(ad_entities, "MAX_PAGES", 3)
    api, session = _api({"/sb/v4/campaigns/list": [
        {"campaigns": [], "nextToken": f"page-{number}"} for number in range(3)
    ]})

    with pytest.raises(AdsApiError, match="exceeded 3 pages"):
        fetch_sb_campaigns(api, "555")
    assert len(session.calls) == 3


def test_a_token_page_that_is_not_an_object_is_refused():
    api, _ = _api({"/sb/v4/campaigns/list": [[_sb_campaign()]]})

    with pytest.raises(AdsApiError):
        fetch_sb_campaigns(api, "555")


@pytest.mark.parametrize("listing", [TOKEN_LISTINGS[0], OFFSET_LISTINGS[2]], ids=_by_path)
def test_a_page_that_is_not_json_is_refused(listing):
    api, _ = _api({listing.path: [_Unreadable(200)]})

    with pytest.raises(AdsApiError):
        listing.fetcher(api, "555")


@pytest.mark.parametrize("listing", OFFSET_LISTINGS, ids=_by_path)
def test_offset_listings_read_on_until_a_short_page(listing):
    api, session = _api({listing.path: [
        [listing.factory(number) for number in range(1, 5001)],
        [listing.factory(5001)],
    ]})

    rows = listing.fetcher(api, "555")

    assert [call["url"].split("?")[1] for call in session.calls_to(listing.path)] == [
        "startIndex=0&count=5000&stateFilter=enabled,paused",
        "startIndex=5000&count=5000&stateFilter=enabled,paused",
    ]
    assert _ids(rows) == [str(number) for number in range(1, 5002)]


def test_an_exactly_full_last_offset_page_ends_on_an_empty_read():
    api, session = _api({"/sd/targets": [[_sd_target(number) for number in range(1, 5001)], []]})

    rows = fetch_sd_targets(api, "555")

    assert len(session.calls_to("/sd/targets")) == 2
    assert len(rows) == 5000


def test_an_offset_listing_that_never_runs_short_is_cut_off(monkeypatch):
    monkeypatch.setattr(ad_entities, "MAX_PAGES", 2)
    monkeypatch.setattr(ad_entities, "OFFSET_PAGE_SIZE", 1)
    api, session = _api({"/sd/campaigns": [[_sd_campaign(1)], [_sd_campaign(2)]]})

    with pytest.raises(AdsApiError, match="exceeded 2 pages"):
        fetch_sd_campaigns(api, "555")
    assert [call["url"].split("?")[1] for call in session.calls] == [
        "startIndex=0&count=1&stateFilter=enabled,paused",
        "startIndex=1&count=1&stateFilter=enabled,paused",
    ]


def test_an_offset_page_that_is_not_a_list_is_refused():
    api, _ = _api({"/sd/campaigns": [{"code": "SERVER_IS_BUSY"}]})

    with pytest.raises(AdsApiError):
        fetch_sd_campaigns(api, "555")


def test_sp_keywords_map_to_keyword_rows():
    api, _ = _api({"/sp/keywords/list": [{"keywords": [_sp_keyword(11)]}]})

    assert fetch_sp_targets(api, "555") == [{
        "ad_product": "SP", "target_id": "11", "campaign_id": "31", "ad_group_id": "21",
        "target_kind": "keyword", "target_text": "demo shorts", "match_type": "EXACT",
        "state": "ENABLED", "bid": 1.25,
    }]


@pytest.mark.parametrize("group, text", [
    ("QUERY_HIGH_REL_MATCHES", "close-match"),
    ("QUERY_BROAD_REL_MATCHES", "loose-match"),
    ("ASIN_SUBSTITUTE_RELATED", "substitutes"),
    ("ASIN_ACCESSORY_RELATED", "complements"),
])
def test_sp_auto_targets_are_named_like_the_sptargeting_report(group, text):
    clause = _sp_clause(12, [{"type": group}], expression_type="AUTO")
    api, _ = _api({"/sp/targets/list": [{"targetingClauses": [clause]}]})

    assert fetch_sp_targets(api, "555") == [{
        "ad_product": "SP", "target_id": "12", "campaign_id": "31", "ad_group_id": "21",
        "target_kind": "auto", "target_text": text, "match_type": "", "state": "PAUSED", "bid": 0.8,
    }]


@pytest.mark.parametrize("sp_type, camel_type, value, text", [
    ("ASIN_SAME_AS", "asinSameAs", "B0DEMO0001", 'asin="B0DEMO0001"'),
    ("ASIN_CATEGORY_SAME_AS", "asinCategorySameAs", "Demo Bras", 'category="Demo Bras"'),
    ("ASIN_BRAND_SAME_AS", "asinBrandSameAs", "Demo Brand", 'brand="Demo Brand"'),
    ("ASIN_PRICE_LESS_THAN", "asinPriceLessThan", "25", "price<25"),
    ("ASIN_PRICE_GREATER_THAN", "asinPriceGreaterThan", "25", "price>25"),
    ("ASIN_PRICE_BETWEEN", "asinPriceBetween", "13.99-26", "price=13.99-26"),
    ("ASIN_REVIEW_RATING_LESS_THAN", "asinReviewRatingLessThan", "4", "rating<4"),
    ("ASIN_REVIEW_RATING_GREATER_THAN", "asinReviewRatingGreaterThan", "3", "rating>3"),
    ("ASIN_REVIEW_RATING_BETWEEN", "asinReviewRatingBetween", "3-5", "rating=3-5"),
])
def test_one_formatter_writes_sp_sb_and_sd_product_targets_alike(sp_type, camel_type, value, text):
    api, _ = _api({
        "/sp/targets/list": [{"targetingClauses": [_sp_clause(12, [{"type": sp_type, "value": value}])]}],
        "/sb/targets/list": [{"targets": [_sb_target(14, [{"type": camel_type, "value": value}])]}],
        "/sd/targets": [[_sd_target(16, [{"type": camel_type, "value": value}])]],
    })

    rows = fetch_sp_targets(api, "555") + fetch_sb_targets(api, "555") + fetch_sd_targets(api, "555")

    assert [(row["target_kind"], row["target_text"]) for row in rows] == [("product", text)] * 3


def test_several_predicates_are_joined_in_their_order():
    clause = _sp_clause(12, [
        {"type": "ASIN_CATEGORY_SAME_AS", "value": "Demo Bras"},
        {"type": "ASIN_BRAND_SAME_AS", "value": "Demo Brand"},
        {"type": "ASIN_PRICE_BETWEEN", "value": "13.99-26"},
        {"type": "ASIN_REVIEW_RATING_GREATER_THAN", "value": "4"},
    ])
    api, _ = _api({"/sp/targets/list": [{"targetingClauses": [clause]}]})

    [row] = fetch_sp_targets(api, "555")

    assert row["target_text"] == 'category="Demo Bras" brand="Demo Brand" price=13.99-26 rating>4'


def test_an_unknown_predicate_type_keeps_its_own_name():
    api, _ = _api({
        "/sp/targets/list": [{"targetingClauses": [
            _sp_clause(12, [{"type": "ASIN_EXPANDED_FROM", "value": "B0DEMO0001"}])]}],
        "/sd/targets": [[_sd_target(16, [{"type": "asinGenreSameAs", "value": "Demo Genre"}])]],
    })

    texts = [row["target_text"] for row in fetch_sp_targets(api, "555") + fetch_sd_targets(api, "555")]

    assert texts == ['asin-expanded-from="B0DEMO0001"', 'asin-genre-same-as="Demo Genre"']


def test_target_text_prefers_resolved_names_and_falls_back_to_the_raw_expression():
    # The raw expression carries a category's node id; the resolved one carries its name.
    resolved = _sp_clause(12, expression=[{"type": "ASIN_CATEGORY_SAME_AS", "value": "2376204011"}],
                          resolvedExpression=[{"type": "ASIN_CATEGORY_SAME_AS", "value": "Demo Bras"}])
    raw_only = _sp_clause(13, [{"type": "ASIN_SAME_AS", "value": "B0DEMO0001"}], resolvedExpression=[])
    api, _ = _api({"/sp/targets/list": [{"targetingClauses": [resolved, raw_only]}]})

    assert [row["target_text"] for row in fetch_sp_targets(api, "555")] == [
        'category="Demo Bras"', 'asin="B0DEMO0001"']


def test_sb_keywords_come_back_with_upper_case_enums():
    api, _ = _api({"/sb/keywords": [[_sb_keyword(13, matchType="phrase", state="paused")]]})

    assert fetch_sb_targets(api, "555") == [{
        "ad_product": "SB", "target_id": "13", "campaign_id": "32", "ad_group_id": "22",
        "target_kind": "keyword", "target_text": "demo bra", "match_type": "PHRASE",
        "state": "PAUSED", "bid": 2.5,
    }]


def test_sb_product_targets_map_to_product_rows():
    api, _ = _api({"/sb/targets/list": [{"targets": [_sb_target(14)]}]})

    assert fetch_sb_targets(api, "555") == [{
        "ad_product": "SB", "target_id": "14", "campaign_id": "32", "ad_group_id": "22",
        "target_kind": "product", "target_text": 'asin="B0DEMO0002"', "match_type": "",
        "state": "ENABLED", "bid": 1.5,
    }]


def test_sb_themes_are_named_like_the_sbtargeting_report():
    api, _ = _api({"/sb/themes/list": [{"themes": [
        _sb_theme(15),
        _sb_theme(16, themeType="KEYWORDS_RELATED_TO_YOUR_LANDING_PAGES"),
    ]}]})

    rows = fetch_sb_targets(api, "555")

    assert rows[0] == {
        "ad_product": "SB", "target_id": "15", "campaign_id": "32", "ad_group_id": "22",
        "target_kind": "theme", "target_text": "keywords-related-to-your-brand", "match_type": "",
        "state": "ENABLED", "bid": 3.0,
    }
    assert rows[1]["target_text"] == "keywords-related-to-your-landing-pages"


def test_sb_targets_and_themes_keep_only_the_enabled_and_paused_ones():
    # Neither listing is filtered by state on Amazon's side.
    api, _ = _api({
        "/sb/targets/list": [{"targets": [
            _sb_target(1), _sb_target(2, state="paused"), _sb_target(3, state="archived")]}],
        "/sb/themes/list": [{"themes": [_sb_theme(4, state="archived"), _sb_theme(5, state="paused")]}],
    })

    rows = fetch_sb_targets(api, "555")

    assert [(row["target_id"], row["state"]) for row in rows] == [
        ("1", "ENABLED"), ("2", "PAUSED"), ("5", "PAUSED")]


def test_sb_campaigns_map_to_campaign_rows():
    api, _ = _api({"/sb/v4/campaigns/list": [{"campaigns": [_sb_campaign(41)]}]})

    assert fetch_sb_campaigns(api, "555") == [{
        "ad_product": "SB", "campaign_id": "41", "name": "Demo - SBV - KW", "state": "ENABLED",
        "budget_amount": 5.0, "budget_type": "DAILY", "cost_type": "CPC", "portfolio_id": "51",
        "start_date": "2026-03-05", "is_multi_ad_groups": False, "goal": "PAGE_VISIT", "tactic": "",
        "bid_strategy": "AUTOMATED",
    }]


@pytest.mark.parametrize("bidding, expected", [
    pytest.param({"bidOptimization": True, "bidOptimizationStrategy": "MAXIMIZE_IMMEDIATE_SALES"},
                 "MAXIMIZE_IMMEDIATE_SALES", id="automated"),
    pytest.param({"bidOptimization": True, "bidOptimizationStrategy": "MAXIMIZE_NEW_TO_BRAND_CUSTOMERS"},
                 "MAXIMIZE_NEW_TO_BRAND_CUSTOMERS", id="new-to-brand"),
    # Off, the strategy Amazon still sends means nothing: the bids are the AM's own.
    pytest.param({"bidOptimization": False, "bidOptimizationStrategy": "MAXIMIZE_IMMEDIATE_SALES",
                  "bidAdjustmentsByPlacement": [{"percentage": -5, "placement": "HOME"}]}, "MANUAL", id="manual"),
    pytest.param({"bidOptimization": "false"}, "MANUAL", id="as-text"),
    pytest.param({}, "", id="without-bidding"),
])
def test_an_sb_campaign_keeps_its_bid_strategy(bidding, expected):
    api, _ = _api({"/sb/v4/campaigns/list": [{"campaigns": [_sb_campaign(41, bidding=bidding)]}]})

    assert fetch_sb_campaigns(api, "555")[0]["bid_strategy"] == expected


def test_an_sd_campaign_takes_the_bid_optimization_of_its_ad_groups():
    api, session = _api({
        "/sd/campaigns": [[_sd_campaign(61), _sd_campaign(62), _sd_campaign(63)]],
        "/sd/adGroups": [[{"adGroupId": 71, "campaignId": 61, "bidOptimization": "conversions"},
                          {"adGroupId": 72, "campaignId": 62, "bidOptimization": "clicks"},
                          {"adGroupId": 73, "campaignId": 62, "bidOptimization": "reach"}]],
    })

    rows = fetch_sd_campaigns(api, "555")

    assert [row["bid_strategy"] for row in rows] == ["conversions", "clicks,reach", ""]
    [call] = session.calls_to("/sd/adGroups")
    assert "stateFilter=enabled,paused" in call["url"]


def test_an_account_without_sd_campaigns_never_lists_ad_groups():
    api, session = _api()

    assert fetch_sd_campaigns(api, "555") == []
    assert session.calls_to("/sd/adGroups") == []


def test_an_sb_campaign_without_its_optional_fields_leaves_them_empty():
    # Amazon omits portfolioId entirely when the campaign is in no portfolio.
    raw = _sb_campaign(41)
    for key in ("portfolioId", "costType", "goal", "isMultiAdGroupsEnabled"):
        raw.pop(key)
    api, _ = _api({"/sb/v4/campaigns/list": [{"campaigns": [raw]}]})

    [row] = fetch_sb_campaigns(api, "555")

    assert (row["portfolio_id"], row["cost_type"], row["goal"], row["is_multi_ad_groups"]) == ("", "", "", None)


def test_sd_campaigns_map_to_campaign_rows():
    api, _ = _api({"/sd/campaigns": [[
        _sd_campaign(61), _sd_campaign(62, costType="vcpm", budgetType="lifetime", state="paused"),
    ]]})

    rows = fetch_sd_campaigns(api, "555")

    assert rows[0] == {
        "ad_product": "SD", "campaign_id": "61", "name": "Demo - SD - Products", "state": "ENABLED",
        "budget_amount": 15.0, "budget_type": "DAILY", "cost_type": "CPC", "portfolio_id": "52",
        "start_date": "2020-10-20", "is_multi_ad_groups": None, "goal": "", "tactic": "T00020", "bid_strategy": "",
    }
    assert (rows[1]["cost_type"], rows[1]["budget_type"], rows[1]["state"]) == ("VCPM", "LIFETIME", "PAUSED")


@pytest.mark.parametrize("start_date, expected", [
    ("20201020", "2020-10-20"),
    ("2020-10-20", "2020-10-20"),
    ("20201340", None),
    ("not-a-date", None),
])
def test_sd_start_dates_come_out_as_iso_days(start_date, expected):
    api, _ = _api({"/sd/campaigns": [[_sd_campaign(61, startDate=start_date)]]})

    assert fetch_sd_campaigns(api, "555")[0]["start_date"] == expected


def test_sd_targets_map_to_target_rows():
    without_bid = _sd_target(17)
    del without_bid["bid"]
    api, _ = _api({"/sd/targets": [[_sd_target(16, state="paused"), without_bid]]})

    rows = fetch_sd_targets(api, "555")

    assert rows[0] == {
        "ad_product": "SD", "target_id": "16", "campaign_id": "33", "ad_group_id": "23",
        "target_kind": "product", "target_text": 'asin="B0DEMO0003"', "match_type": "",
        "state": "PAUSED", "bid": 1.0,
    }
    # A target without a bid of its own stays empty rather than zero.
    assert rows[1]["bid"] is None


@pytest.mark.parametrize("expression_type, predicates, kind, text", [
    pytest.param("manual", [{"type": "asinCategorySameAs", "value": "Demo Panties"},
                            {"type": "asinPriceGreaterThan", "value": "26"}],
                 "product", 'category="Demo Panties" price>26', id="product"),
    pytest.param("manual", [{"type": "views", "value": [{"type": "asinCategorySameAs", "value": "Demo Bras"},
                                                        {"type": "asinPriceGreaterThan", "value": "25"},
                                                        {"type": "lookback", "value": "30"}]}],
                 "audience", 'views=(category="Demo Bras" price>25 lookback=30)', id="views"),
    pytest.param("manual", [{"type": "purchases", "value": [{"type": "exactProduct"},
                                                            {"type": "lookback", "value": "30"}]}],
                 "audience", "purchases=(exact-product lookback=30)", id="purchases"),
    pytest.param("manual", [{"type": "audience", "value": [{"type": "audienceSameAs", "value": "Demo Shoppers"}]}],
                 "audience", 'audience=(audience="Demo Shoppers")', id="audience"),
    pytest.param("auto", [{"type": "similarProduct"}], "auto", "similar-product", id="auto"),
])
def test_sd_targets_are_classified_by_their_expression(expression_type, predicates, kind, text):
    api, _ = _api({"/sd/targets": [[_sd_target(16, predicates, expression_type)]]})

    [row] = fetch_sd_targets(api, "555")

    assert (row["target_kind"], row["target_text"]) == (kind, text)


def test_sd_audience_text_uses_the_resolved_names_inside_the_nesting():
    target = _sd_target(
        16,
        expression=[{"type": "views", "value": [{"type": "asinCategorySameAs", "value": "2376204011"},
                                                {"type": "lookback", "value": "30"}]}],
        resolvedExpression=[{"type": "views", "value": [{"type": "asinCategorySameAs", "value": "Demo Bras"},
                                                        {"type": "lookback", "value": "30"}]}],
    )
    api, _ = _api({"/sd/targets": [[target]]})

    assert fetch_sd_targets(api, "555")[0]["target_text"] == 'views=(category="Demo Bras" lookback=30)'


def test_ids_come_out_as_exact_text_even_at_eighteen_digits():
    # 144000000000000001 has no exact float; any trip through float would change its last digits.
    keyword = _sb_keyword(144000000000000001, adGroupId=144000000000000002, campaignId=144000000000000003)
    api, _ = _api({"/sb/keywords": [[keyword]], "/sd/campaigns": [[_sd_campaign(123456789012345.0)]]})

    [keyword_row] = fetch_sb_targets(api, "555")
    [campaign_row] = fetch_sd_campaigns(api, "555")

    assert (keyword_row["target_id"], keyword_row["ad_group_id"], keyword_row["campaign_id"]) == (
        "144000000000000001", "144000000000000002", "144000000000000003")
    assert campaign_row["campaign_id"] == "123456789012345"


def test_every_target_row_carries_every_column_of_the_table():
    # PostgREST takes a bulk upsert only when every object in it has the same keys.
    api, _ = _api({
        "/sp/keywords/list": [{"keywords": [_sp_keyword(1)]}],
        "/sp/targets/list": [{"targetingClauses": [
            _sp_clause(2), _sp_clause(3, [{"type": "QUERY_HIGH_REL_MATCHES"}], "AUTO")]}],
        "/sb/keywords": [[_sb_keyword(4)]],
        "/sb/targets/list": [{"targets": [_sb_target(5)]}],
        "/sb/themes/list": [{"themes": [_sb_theme(6)]}],
        "/sd/targets": [[_sd_target(7), _sd_target(8, [{"type": "similarProduct"}], "auto"),
                         _sd_target(9, [{"type": "views", "value": [{"type": "exactProduct"}]}])]],
    })

    rows_by_product = {
        "SP": fetch_sp_targets(api, "555"),
        "SB": fetch_sb_targets(api, "555"),
        "SD": fetch_sd_targets(api, "555"),
    }

    assert {product: [row["target_kind"] for row in rows] for product, rows in rows_by_product.items()} == {
        "SP": ["keyword", "product", "auto"],
        "SB": ["keyword", "product", "theme"],
        "SD": ["product", "auto", "audience"],
    }
    for product, rows in rows_by_product.items():
        assert all(set(row) == TARGET_COLUMNS and row["ad_product"] == product for row in rows)


def test_every_campaign_row_carries_every_column_even_from_a_bare_listing():
    api, _ = _api({"/sb/v4/campaigns/list": [{"campaigns": [{"campaignId": "41"}]}],
                   "/sd/campaigns": [[{"campaignId": 61}]]})

    rows = fetch_sb_campaigns(api, "555") + fetch_sd_campaigns(api, "555")

    empty = {"name": "", "state": "", "budget_amount": None, "budget_type": "", "cost_type": "",
             "portfolio_id": "", "start_date": None, "is_multi_ad_groups": None, "goal": "", "tactic": "",
             "bid_strategy": ""}
    assert rows == [{"ad_product": "SB", "campaign_id": "41", **empty},
                    {"ad_product": "SD", "campaign_id": "61", **empty}]


def test_listed_items_without_an_id_are_skipped():
    api, _ = _api({
        "/sp/keywords/list": [{"keywords": [_sp_keyword(1), _sp_keyword(keywordId=None), "not-an-item"]}],
        "/sd/targets": [[_sd_target(targetId="")]],
    })

    assert _ids(fetch_sp_targets(api, "555")) == ["1"]
    assert fetch_sd_targets(api, "555") == []


@pytest.mark.parametrize("fetcher", [
    fetch_sp_targets, fetch_sp_ad_groups, fetch_sb_campaigns, fetch_sb_targets, fetch_sd_campaigns,
    fetch_sd_targets,
    pytest.param(partial(fetch_negative_page, listing_index=0, next_token=""), id="fetch_negative_page"),
])
def test_access_denied_propagates_to_the_caller(fetcher):
    # Every listing refuses, so whichever one the fetcher reads first raises.
    api, _ = _api({path: [_FakeResponse(403, {"code": "UNAUTHORIZED"})] for path in EMPTY_PAGES})

    with pytest.raises(AdsAccessDenied):
        fetcher(api, "555")


MARKETPLACE_WITHOUT_SB_TARGETING = {"code": "400", "details": "Marketplace A39IBJ37TRP1C6 do not have access to "
                                                               "Sponsored Brands product targeting functionality"}


@pytest.mark.parametrize("path", ["/sb/targets/list", "/sb/themes/list"])
def test_an_sb_feature_the_marketplace_does_not_offer_lists_as_empty_instead_of_failing(path):
    """Shapermint AU: /sb/targets/list answers 400 because AU has no SB product targeting. Failing the
    listing left the account without its SB campaigns and their reports too."""
    api, _ = _api({"/sb/keywords": [[_sb_keyword(13)]],
                   "/sb/targets/list": [{"targets": [_sb_target(14)]}],
                   "/sb/themes/list": [{"themes": [_sb_theme(15)]}],
                   path: [_FakeResponse(400, MARKETPLACE_WITHOUT_SB_TARGETING)]})

    rows = fetch_sb_targets(api, "555")

    assert "13" in _ids(rows) and len(rows) == 2


def test_any_other_bad_request_still_fails_the_listing():
    api, _ = _api({"/sb/targets/list": [_FakeResponse(400, {"code": "400", "details": "Invalid maxResults"})]})

    with pytest.raises(AdsApiError, match="HTTP 400"):
        fetch_sb_targets(api, "555")


def test_throttling_that_outlasts_the_retries_propagates_to_the_caller():
    api, session = _api({"/sd/targets": [_FakeResponse(429)] * 4})

    with pytest.raises(AdsThrottled):
        fetch_sd_targets(api, "555")
    assert len(session.calls) == 4


def _saved_target(target_id, ad_product="SB", **overrides):
    return {"ad_product": ad_product, "target_id": target_id, "campaign_id": "32", "ad_group_id": "22",
            "target_kind": "keyword", "target_text": "demo bra", "match_type": "EXACT", "state": "ENABLED",
            "bid": 1.0, **overrides}


def _saved_campaign(campaign_id, ad_product="SB", **overrides):
    return {"ad_product": ad_product, "campaign_id": campaign_id, "name": "Demo campaign", "state": "ENABLED",
            "budget_amount": 5.0, "budget_type": "DAILY", "cost_type": "CPC", "portfolio_id": "",
            "start_date": None, "is_multi_ad_groups": None, "goal": "", "tactic": "", **overrides}


def test_save_targets_upserts_each_target_with_the_profile_and_timestamp():
    rest = _FakeRest()

    written = save_targets(rest, "555", "SB", [_saved_target("1"), _saved_target("2")], SEEN_AT)

    [(table, rows, on_conflict)] = rest.upserts
    assert written == 2
    assert table == TARGETS_TABLE == "ads_target"
    assert on_conflict == "profile_id,ad_product,target_id"
    assert rows == [{**_saved_target(target_id), "profile_id": "555", "seen_at": SEEN_AT.isoformat()}
                    for target_id in ("1", "2")]


def test_save_targets_keeps_one_row_per_target_so_the_bulk_upsert_is_accepted():
    rest = _FakeRest()

    written = save_targets(rest, "555", "SB", [_saved_target("1", bid=1.0), _saved_target("1", bid=2.0)], SEEN_AT)

    [(_, rows, _)] = rest.upserts
    assert written == 1
    assert [row["bid"] for row in rows] == [2.0]


def test_save_targets_sends_a_large_account_in_batches_of_a_thousand():
    rest = _FakeRest()

    written = save_targets(rest, "555", "SP", [_saved_target(str(number), "SP") for number in range(2500)],
                           SEEN_AT)

    assert written == 2500
    assert [len(rows) for _, rows, _ in rest.upserts] == [1000, 1000, 500]
    assert {(table, on_conflict) for table, _, on_conflict in rest.upserts} == {
        ("ads_target", "profile_id,ad_product,target_id")}
    assert len({row["target_id"] for _, rows, _ in rest.upserts for row in rows}) == 2500


def test_save_product_campaigns_upserts_each_campaign_with_the_profile_and_timestamp():
    rest = _FakeRest()

    written = save_product_campaigns(rest, "555", [_saved_campaign("41"), _saved_campaign("61", "SD")], SEEN_AT)

    [(table, rows, on_conflict)] = rest.upserts
    assert written == 2
    assert table == PRODUCT_CAMPAIGNS_TABLE == "ads_sb_sd_campaign"
    assert on_conflict == "profile_id,ad_product,campaign_id"
    assert rows[1] == {**_saved_campaign("61", "SD"), "profile_id": "555", "seen_at": SEEN_AT.isoformat()}


def test_save_product_campaigns_keeps_one_row_per_product_and_campaign():
    rest = _FakeRest()

    written = save_product_campaigns(rest, "555", [
        _saved_campaign("41", name="First"), _saved_campaign("41", name="Second"), _saved_campaign("41", "SD"),
    ], SEEN_AT)

    [(_, rows, _)] = rest.upserts
    assert written == 2
    assert [(row["ad_product"], row["name"]) for row in rows] == [("SB", "Second"), ("SD", "Demo campaign")]


def test_save_product_campaigns_sends_batches_of_a_thousand():
    rest = _FakeRest()

    written = save_product_campaigns(rest, "555", [_saved_campaign(str(number)) for number in range(2001)],
                                     SEEN_AT)

    assert written == 2001
    assert [len(rows) for _, rows, _ in rest.upserts] == [1000, 1000, 1]


def test_saving_nothing_writes_nothing():
    rest = _FakeRest()

    assert save_targets(rest, "555", "SP", [], SEEN_AT) == 0
    assert save_targets(rest, "555", "SP", [_saved_target("", "SP")], SEEN_AT) == 0
    assert save_product_campaigns(rest, "555", [], SEEN_AT) == 0
    assert save_ad_groups(rest, "555", "SP", [], SEEN_AT) == 0
    assert save_negatives(rest, "555", "SP", [_saved_negative("")], SEEN_AT) == 0
    assert rest.upserts == []


def test_sp_product_ads_map_to_the_asin_and_sku_each_ad_group_advertises():
    api, _ = _api({"/sp/productAds/list": [{"productAds": [
        _sp_product_ad(17), _sp_product_ad(adId=18.0, adGroupId=22.0, sku=None, state="PAUSED"), {"adId": ""}]}]})

    rows = fetch_sp_product_ads(api, "555")

    assert rows == [
        {"ad_id": "17", "campaign_id": "31", "ad_group_id": "21", "asin": "B0DEMO0004", "sku": "DEMO-SKU",
         "state": "ENABLED"},
        {"ad_id": "18", "campaign_id": "31", "ad_group_id": "22", "asin": "B0DEMO0004", "sku": "", "state": "PAUSED"},
    ]


def test_save_product_ads_keeps_one_row_per_ad_with_the_profile_and_timestamp():
    rest = _FakeRest()
    ad = {"ad_id": "17", "campaign_id": "31", "ad_group_id": "21", "asin": "B0DEMO0004", "sku": "S", "state": "ENABLED"}

    written = save_product_ads(rest, "555", [ad, {**ad, "state": "PAUSED"}, {**ad, "ad_id": ""}], SEEN_AT)

    [(table, rows, on_conflict)] = rest.upserts
    assert (written, table, on_conflict) == (1, PRODUCT_ADS_TABLE, "profile_id,ad_id")
    assert rows == [{**ad, "state": "PAUSED", "profile_id": "555", "seen_at": SEEN_AT.isoformat()}]


def test_sp_ad_groups_map_to_ad_group_rows_with_their_default_bid():
    without_bid = _sp_ad_group(22, state="paused")
    del without_bid["defaultBid"]
    api, _ = _api({"/sp/adGroups/list": [{"adGroups": [
        _sp_ad_group(21), without_bid, _sp_ad_group(23, defaultBid=""), {"adGroupId": ""}]}]})

    rows = fetch_sp_ad_groups(api, "555")

    assert rows == [
        {"ad_group_id": "21", "campaign_id": "31", "name": "Demo - Exact", "state": "ENABLED", "default_bid": 0.75},
        # A missing or empty default bid stays unknown, never zero: zero would read as a real bid.
        {"ad_group_id": "22", "campaign_id": "31", "name": "Demo - Exact", "state": "PAUSED", "default_bid": None},
        {"ad_group_id": "23", "campaign_id": "31", "name": "Demo - Exact", "state": "ENABLED", "default_bid": None},
    ]


def test_ad_group_ids_come_out_as_exact_text_even_at_eighteen_digits():
    api, _ = _api({"/sp/adGroups/list": [{"adGroups": [
        _sp_ad_group(adGroupId=144000000000000004, campaignId=144000000000000003)]}]})

    [row] = fetch_sp_ad_groups(api, "555")

    assert (row["ad_group_id"], row["campaign_id"]) == ("144000000000000004", "144000000000000003")


@pytest.mark.parametrize("listing_index, path, media_type", [
    pytest.param(0, "/sp/negativeKeywords/list", "application/vnd.spNegativeKeyword.v3+json",
                 id="sp-negative-keywords"),
    pytest.param(1, "/sp/campaignNegativeKeywords/list", "application/vnd.spCampaignNegativeKeyword.v3+json",
                 id="sp-campaign-negative-keywords"),
    pytest.param(2, "/sp/negativeTargets/list", "application/vnd.spNegativeTargetingClause.v3+json",
                 id="sp-negative-targets"),
    pytest.param(3, "/sp/campaignNegativeTargets/list", "application/vnd.spCampaignNegativeTargetingClause.v3+json",
                 id="sp-campaign-negative-targets"),
])
def test_a_negative_page_sends_the_verified_request(listing_index, path, media_type):
    api, session = _api()

    fetch_negative_page(api, "555", listing_index, "")
    fetch_negative_page(api, "555", listing_index, "page-2")

    first, later = session.calls_to(path)
    first_body = {"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 1000}
    assert (first["method"], first["url"], first["json"]) == ("POST", HOST + path, first_body)
    # A later page repeats the filters and page size; only the token is added.
    assert later["json"] == {**first_body, "nextToken": "page-2"}
    for call in (first, later):
        assert call["headers"].get("Content-Type") == media_type
        assert call["headers"].get("Accept") == media_type
        assert call["headers"]["Amazon-Advertising-API-Scope"] == "555"
    assert [listing.path for listing in SP_NEGATIVE_LISTINGS] == NEGATIVE_PATHS


def test_a_negative_page_carries_its_rows_and_the_token_of_the_next_page():
    api, _ = _api({"/sp/campaignNegativeKeywords/list": [
        {"campaignNegativeKeywords": [_sp_campaign_negative_keyword(82)], "nextToken": "page-2"},
        {"campaignNegativeKeywords": [_sp_campaign_negative_keyword(83)]},
    ]})

    first = fetch_negative_page(api, "555", 1, "")
    last = fetch_negative_page(api, "555", 1, first.next_token)

    assert isinstance(first, NegativePage)
    assert (_ids(first.rows), first.next_token) == (["82"], "page-2")
    # The last page of a listing has no token: the caller moves on to the next listing.
    assert (_ids(last.rows), last.next_token) == (["83"], "")


def test_a_negative_page_that_hands_back_the_token_it_was_sent_is_an_error():
    api, _ = _api({"/sp/negativeKeywords/list": [
        {"negativeKeywords": [_sp_negative_keyword(81)], "nextToken": "page-2"},
        {"negativeKeywords": [_sp_negative_keyword(81)], "nextToken": "page-2"},
    ]})

    first = fetch_negative_page(api, "555", 0, "")

    # A run in parts only keeps its last token: answered again, the same page would come back every tick.
    with pytest.raises(AdsApiError, match="page token it was sent"):
        fetch_negative_page(api, "555", 0, first.next_token)


def _first_negative_pages(api):
    """The rows of the first page of each negative listing, in their order."""
    return [row for index in range(len(SP_NEGATIVE_LISTINGS))
            for row in fetch_negative_page(api, "555", index, "").rows]


def test_sp_negatives_of_the_four_listings_share_one_row_shape():
    campaign_brand = _sp_campaign_negative_target(
        84, expression=[{"type": "ASIN_BRAND_SAME_AS", "value": "8412345"}],
        resolvedExpression=[{"type": "ASIN_BRAND_SAME_AS", "value": "Rival Brand"}])
    api, session = _api({
        "/sp/negativeKeywords/list": [{"negativeKeywords": [_sp_negative_keyword(81)]}],
        "/sp/campaignNegativeKeywords/list": [{"campaignNegativeKeywords": [
            _sp_campaign_negative_keyword(82, matchType="negative_phrase", state="paused")]}],
        "/sp/negativeTargets/list": [{"negativeTargetingClauses": [_sp_negative_target(83)]}],
        "/sp/campaignNegativeTargets/list": [{"campaignNegativeTargetingClauses": [campaign_brand]}],
    })

    rows = _first_negative_pages(api)

    assert rows == [
        {"negative_id": "81", "level": "ad_group", "negative_kind": "keyword", "campaign_id": "31",
         "ad_group_id": "21", "negative_text": "free demo", "match_type": "NEGATIVE_EXACT", "state": "ENABLED"},
        {"negative_id": "82", "level": "campaign", "negative_kind": "keyword", "campaign_id": "31",
         "ad_group_id": "", "negative_text": "cheap demo", "match_type": "NEGATIVE_PHRASE", "state": "PAUSED"},
        {"negative_id": "83", "level": "ad_group", "negative_kind": "product", "campaign_id": "31",
         "ad_group_id": "21", "negative_text": 'asin="B0RIVAL001"', "match_type": "", "state": "ENABLED"},
        # The resolved expression names the brand where the raw one carries its id.
        {"negative_id": "84", "level": "campaign", "negative_kind": "product", "campaign_id": "31",
         "ad_group_id": "", "negative_text": 'brand="Rival Brand"', "match_type": "", "state": "ENABLED"},
    ]
    assert all(set(row) == NEGATIVE_COLUMNS for row in rows)
    assert [_path(call["url"]) for call in session.calls] == NEGATIVE_PATHS


def test_negative_items_without_their_id_are_skipped():
    api, _ = _api({
        "/sp/negativeKeywords/list": [{"negativeKeywords": [
            _sp_negative_keyword(81), _sp_negative_keyword(keywordId="")]}],
        "/sp/campaignNegativeTargets/list": [{"campaignNegativeTargetingClauses": [
            _sp_campaign_negative_target(targetId=None), "not-an-item"]}],
    })

    rows = _first_negative_pages(api)

    assert _ids(rows) == ["81"]


def _saved_ad_group(ad_group_id, **overrides):
    return {"ad_group_id": ad_group_id, "campaign_id": "31", "name": "Demo - Exact", "state": "ENABLED",
            "default_bid": 0.75, **overrides}


def _saved_negative(negative_id, **overrides):
    return {"negative_id": negative_id, "level": "ad_group", "negative_kind": "keyword", "campaign_id": "31",
            "ad_group_id": "21", "negative_text": "free demo", "match_type": "NEGATIVE_EXACT", "state": "ENABLED",
            **overrides}


def test_save_ad_groups_keeps_one_row_per_ad_group_with_the_product_profile_and_timestamp():
    rest = _FakeRest()

    written = save_ad_groups(rest, "555", "SP", [
        _saved_ad_group("21"), _saved_ad_group("21", default_bid=0.9), _saved_ad_group("22"), _saved_ad_group(""),
    ], SEEN_AT)

    [(table, rows, on_conflict)] = rest.upserts
    assert (written, table, on_conflict) == (2, AD_GROUPS_TABLE, "profile_id,ad_product,ad_group_id")
    assert AD_GROUPS_TABLE == "ads_ad_group"
    stamp = {"ad_product": "SP", "profile_id": "555", "seen_at": SEEN_AT.isoformat()}
    assert rows == [{**_saved_ad_group("21", default_bid=0.9), **stamp}, {**_saved_ad_group("22"), **stamp}]


def test_save_ad_groups_sends_a_large_account_in_batches_of_a_thousand():
    rest = _FakeRest()

    written = save_ad_groups(rest, "555", "SP", [_saved_ad_group(str(number)) for number in range(2500)], SEEN_AT)

    assert written == 2500
    assert [len(rows) for _, rows, _ in rest.upserts] == [1000, 1000, 500]


def test_save_negatives_keys_each_negative_by_its_level_kind_and_id():
    rest = _FakeRest()

    written = save_negatives(rest, "555", "SP", [
        _saved_negative("81"),
        # The same id in another listing is another negative: the four listings are separate id spaces.
        _saved_negative("81", level="campaign", ad_group_id=""),
        _saved_negative("81", negative_kind="product", negative_text='asin="B0RIVAL001"', match_type=""),
        _saved_negative("81", negative_text="free demo shorts"),
    ], SEEN_AT)

    [(table, rows, on_conflict)] = rest.upserts
    assert (written, table) == (3, NEGATIVES_TABLE)
    assert on_conflict == "profile_id,ad_product,level,negative_kind,negative_id"
    assert NEGATIVES_TABLE == "ads_negative"
    assert [(row["level"], row["negative_kind"], row["negative_text"]) for row in rows] == [
        ("ad_group", "keyword", "free demo shorts"), ("campaign", "keyword", "free demo"),
        ("ad_group", "product", 'asin="B0RIVAL001"')]
    assert all((row["ad_product"], row["profile_id"], row["seen_at"]) == ("SP", "555", SEEN_AT.isoformat())
               for row in rows)


def test_save_negatives_sends_batches_of_a_thousand():
    rest = _FakeRest()

    written = save_negatives(rest, "555", "SP", [_saved_negative(str(number)) for number in range(2001)], SEEN_AT)

    assert written == 2001
    assert [len(rows) for _, rows, _ in rest.upserts] == [1000, 1000, 1]


def test_save_listing_snapshot_keeps_one_row_per_profile_and_listing():
    rest = _FakeRest()
    completed_at = datetime(2026, 9, 18, 10, 9, tzinfo=timezone.utc)

    save_listing_snapshot(rest, "555", "sp_negatives", seen_at=SEEN_AT, rows=371407, completed_at=completed_at)

    [(table, row, on_conflict)] = rest.upserts
    assert (table, on_conflict) == (LISTING_SNAPSHOTS_TABLE, "profile_id,listing")
    assert LISTING_SNAPSHOTS_TABLE == "ads_listing_snapshot"
    assert row == {"profile_id": "555", "listing": "sp_negatives", "seen_at": SEEN_AT.isoformat(), "rows": 371407,
                   "completed_at": completed_at.isoformat()}

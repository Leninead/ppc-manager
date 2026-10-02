"""Live Amazon Ads reads: the request each one sends, what it keeps of the answer, and how a failure reads. No network."""
from __future__ import annotations

import threading
import time
from datetime import date

import pytest

from core.amazon_ads import live_reads
from core.amazon_ads.api_client import AdsAccessDenied, AdsApiError, AdsThrottled
from core.amazon_ads.live_reads import LiveAccount, LiveReadError
from core.amazon_ads.tokens import ConnectionUnavailable
from core.integrations import oauth

ACCOUNT = LiveAccount(profile_id="111", connection_id=1, region="NA", country="MX", currency="MXN",
                      label="Acme · MX")


class _Response:
    def __init__(self, body=None, status: int = 200):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


class _FakeApi:
    """Answers each request with the next scripted body; an exception instance is raised instead."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append({"method": method, "path": path, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, _Response) else _Response(answer)


def test_sponsored_products_budget_recommendations_read_as_a_share_of_100_and_map_by_index():
    api = _FakeApi({"budgetRecommendationsSuccessResults": [
        {"index": 1, "suggestedBudget": 45, "sevenDaysMissedOpportunities": {
            "percentTimeInBudget": 0.62, "estimatedMissedSalesLower": 10, "estimatedMissedSalesUpper": 30,
            "startDate": "2026-09-24", "endDate": "2026-09-30"}},
        {"index": 0, "suggestedBudget": 20, "sevenDaysMissedOpportunities": {"percentTimeInBudget": -1}}],
        "budgetRecommendationsErrorResults": [{"index": 2, "code": "404"}]})

    found = live_reads.budget_recommendations(api, ACCOUNT, "SP", ["c0", "c1", "c2"])

    assert found["c1"]["time_in_budget_pct"] == 62.0
    assert found["c1"]["missed_sales"] == [10, 30]
    assert found["c1"]["window"] == ["2026-09-24", "2026-09-30"]
    assert found["c0"]["time_in_budget_pct"] is None
    assert found["c2"] is None
    call = api.calls[0]
    assert call["path"] == "/sp/campaigns/budgetRecommendations"
    assert call["content_type"] == "application/vnd.budgetrecommendation.v3+json"
    assert call["json_body"] == {"campaignIds": ["c0", "c1", "c2"]}
    assert call["profile_id"] == "111"


def test_brands_and_display_budget_recommendations_already_answer_0_to_100():
    api = _FakeApi({"success": [{"index": 0, "sevenDaysMissedOpportunities": {"percentTimeInBudget": 87.5}}],
                    "error": []})

    found = live_reads.budget_recommendations(api, ACCOUNT, "SB", ["c0"])

    assert found["c0"]["time_in_budget_pct"] == 87.5
    assert api.calls[0]["path"] == "/sb/campaigns/budgetRecommendations"


def test_budget_recommendations_go_in_batches_of_100():
    ids = [f"c{number}" for number in range(150)]
    api = _FakeApi({"budgetRecommendationsSuccessResults": []}, {"budgetRecommendationsSuccessResults": []})

    live_reads.budget_recommendations(api, ACCOUNT, "SD", ids)

    assert [len(call["json_body"]["campaignIds"]) for call in api.calls] == [100, 50]


def test_budget_usage_keys_by_id_and_reads_a_portfolio_without_cap_as_no_budget():
    api = _FakeApi({"success": [
        {"portfolioId": "p1", "budget": 9_999_999_999, "budgetUsagePercent": 0,
         "usageUpdatedTimestamp": "2026-10-01T18:00:00Z"},
        {"portfolioId": "p2", "budget": 300, "budgetUsagePercent": 112.5}]})

    found = live_reads.budget_usage(api, ACCOUNT, "PORTFOLIO", ["p1", "p2"])

    assert found["p1"] == {"budget": None, "usage_pct": 0, "updated_at": "2026-10-01T18:00:00Z"}
    assert found["p2"]["usage_pct"] == 112.5
    assert api.calls[0]["json_body"] == {"portfolioIds": ["p1", "p2"]}


def test_budget_rules_follow_the_next_page_and_keep_what_a_person_reads():
    rule = {"ruleId": "r1", "ruleState": "ACTIVE", "ruleStatus": "ACTIVE", "ruleDetails": {
        "name": "ACoS bajo", "ruleType": "PERFORMANCE", "budgetIncreaseBy": {"type": "PERCENT", "value": 50},
        "performanceMeasureCondition": {"metricName": "ACOS", "comparisonOperator": "LESS_THAN", "threshold": 25},
        "recurrence": {"type": "DAILY"}, "duration": {"dateRangeTypeRuleDuration": {"startDate": "20260901"}}}}
    api = _FakeApi({"budgetRulesForAdvertiserResponse": [rule], "nextToken": "t2"},
                   {"budgetRulesForAdvertiserResponse": [rule]})

    rules = live_reads.budget_rules(api, ACCOUNT, "SP")

    assert len(rules) == 2
    assert rules[0]["condition"] == "ACOS LESS_THAN 25"
    assert rules[0]["increase_pct"] == 50
    assert api.calls[1]["path"] == "/sp/budgetRules?pageSize=30&nextToken=t2"


def test_product_metadata_keeps_stock_price_rank_and_eligibility():
    api = _FakeApi({"ProductMetadataList": [{
        "asin": "B000000001", "sku": "S1", "title": "Producto", "availability": "OUT_OF_STOCK",
        "priceToPay": {"amount": 19.99, "currency": "USD"}, "bestSellerRank": "1234",
        "eligibilityStatus": "INELIGIBLE", "ineligibilityCodes": ["NOT_IN_BUYBOX"]}]})

    rows = live_reads.product_metadata(api, ACCOUNT, ["B000000001"])

    assert rows == [{"asin": "B000000001", "sku": "S1", "title": "Producto", "brand": None, "category": None,
                     "availability": "OUT_OF_STOCK", "price": 19.99, "list_price": None, "currency": "USD",
                     "best_seller_rank": 1234, "eligibility": "INELIGIBLE", "ineligibility_codes": ["NOT_IN_BUYBOX"]}]
    body = api.calls[0]["json_body"]
    assert body["checkEligibility"] and body["checkItemDetails"] and body["pageSize"] == 1


def test_change_history_scopes_campaigns_by_id_and_their_children_by_parent():
    api = _FakeApi({"events": [{"timestamp": 1790873102265, "entityType": "KEYWORD", "entityId": 9,
                                "changeType": "BID_AMOUNT", "previousValue": 1.2, "newValue": 1.5,
                                "metadata": {"campaignId": "c1", "keyword": None}}], "totalRecords": 1})

    result = live_reads.change_history(api, ACCOUNT, days=400, entities=("CAMPAIGN", "KEYWORD"),
                                       change="BID_AMOUNT", campaign_ids=["c1"])

    body = api.calls[0]["json_body"]
    assert body["eventTypes"]["CAMPAIGN"] == {"eventTypeIds": ["c1"], "filters": ["BID_AMOUNT"]}
    assert body["eventTypes"]["KEYWORD"] == {"parents": [{"campaignId": "c1"}], "filters": ["BID_AMOUNT"]}
    assert body["toDate"] - body["fromDate"] == 89 * 86_400_000
    event = result["events"][0]
    assert event["at"].startswith("2026-") and event["before"] == 1.2 and event["after"] == 1.5
    assert event["detail"] == {"campaignId": "c1"}
    assert result["total"] == 1


def test_change_history_without_campaigns_asks_for_the_whole_advertiser():
    api = _FakeApi({"events": [], "totalRecords": 0})

    live_reads.change_history(api, ACCOUNT, days=7, entities=("AD_GROUP",))

    assert api.calls[0]["json_body"]["eventTypes"] == {"AD_GROUP": {"parents": [{"useProfileIdAdvertiser": True}]}}


@pytest.mark.parametrize("read", [
    lambda api: live_reads.change_history(api, ACCOUNT, days=7),
    lambda api: live_reads.store_insights(api, ACCOUNT, "E1", "VISITS", "DATE", date(2026, 9, 1), date(2026, 9, 30)),
])
def test_parallel_history_and_store_reads_of_one_account_go_one_at_a_time(read):
    guard, running, most = threading.Lock(), [0], [0]

    class _SlowApi:
        def request(self, method, path, **kwargs):
            with guard:
                running[0] += 1
                most[0] = max(most[0], running[0])
            time.sleep(0.05)
            with guard:
                running[0] -= 1
            return _Response({"events": [], "totalRecords": 0, "metricsDetails": []})

    readers = [threading.Thread(target=read, args=(_SlowApi(),)) for _ in range(3)]
    for reader in readers:
        reader.start()
    for reader in readers:
        reader.join()

    assert most[0] == 1


@pytest.mark.parametrize("error, what, says", [
    (AdsThrottled("x"), "el historial de cambios", "las consultas del historial de cambios"),
    (AdsThrottled("x"), "los datos de los productos", "las consultas de los datos de los productos"),
    (AdsAccessDenied("x", status=403), "el historial de cambios", "no tiene acceso al historial de cambios"),
    (AdsApiError("x", status=400, body='{"message":"bad"}'), "el historial de cambios", "el pedido del historial"),
])
def test_a_failure_names_what_it_asked_with_del_and_al(error, what, says):
    assert says in str(live_reads.explain(error, ACCOUNT, what))


@pytest.mark.parametrize("kind, text, match, expected", [
    ("keyword", "fajas mujer", "EXACT", {"type": "KEYWORD_EXACT_MATCH", "value": "fajas mujer"}),
    ("auto", "close-match", "", {"type": "CLOSE_MATCH"}),
    ("auto", "substitutes", "", {"type": "SUBSTITUTES"}),
    ("product", 'asin="B000000001"', "", {"type": "PAT_ASIN", "value": "B000000001"}),
    ("product", 'category="123"', "", {"type": "PAT_CATEGORY", "value": "123"}),
    ("product", 'asin-expanded-from="B000000001"', "", None),
    ("keyword", "x", "", None),
])
def test_sponsored_products_targets_become_the_expressions_amazon_prices(kind, text, match, expected):
    assert live_reads.sp_target_expression(kind, text, match) == expected


def test_display_prices_product_and_category_targets_but_not_audiences():
    assert live_reads.sd_target_expression('asin="B000000001"') == {"type": "asinSameAs", "value": "B000000001"}
    assert live_reads.sd_target_expression('category="77"') == {"type": "asinCategorySameAs", "value": "77"}
    assert live_reads.sd_target_expression("views=(exact-product lookback=30)") is None


def test_keyword_recommendations_turn_their_cents_into_the_currency_and_mark_the_targeted_ones():
    api = _FakeApi({"keywordTargetList": [{
        "keyword": "fajas", "userSelectedKeyword": True, "searchTermImpressionShare": 12.5,
        "searchTermImpressionRank": 3,
        "bidInfo": [{"matchType": "EXACT", "suggestedBid": {"rangeStart": 98, "rangeMedian": 129, "rangeEnd": 160}}]}]})

    found = live_reads.sp_keyword_recommendations(api, ACCOUNT, "c1", "g1",
                                                  [{"text": "fajas", "match": "EXACT", "bid": 1.0}])

    assert found == [{"keyword": "fajas", "targeted": True, "impression_share_pct": 12.5, "impression_rank": 3,
                      "suggested_bids": {"EXACT": {"low": 0.98, "suggested": 1.29, "high": 1.6}}}]
    call = api.calls[0]
    assert call["content_type"] == "application/vnd.spkeywordsrecommendation.v5+json"
    assert call["json_body"]["targets"] == [{"keyword": "fajas", "matchType": "EXACT", "userSelectedKeyword": True,
                                             "bid": 1.0}]


def test_bid_recommendations_use_v5_and_order_the_three_suggested_bids():
    api = _FakeApi({"bidRecommendations": [{"theme": "CONVERSION_OPPORTUNITIES",
                                            "bidRecommendationsForTargetingExpressions": [{
                                                "targetingExpression": {"type": "CLOSE_MATCH"},
                                                "bidValues": [{"suggestedBid": 0.8}, {"suggestedBid": 0.52},
                                                              {"suggestedBid": 0.71}]}]}]})

    rows = live_reads.sp_bid_recommendations(api, ACCOUNT, "c1", "g1", [{"type": "CLOSE_MATCH"}])

    assert rows == [{"theme": "CONVERSION_OPPORTUNITIES", "type": "CLOSE_MATCH", "value": None, "low": 0.52,
                     "suggested": 0.71, "high": 0.8}]
    assert api.calls[0]["content_type"] == "application/vnd.spthemebasedbidrecommendation.v5+json"


def test_display_bids_follow_the_campaign_cost_type_and_say_when_amazon_has_none():
    api = _FakeApi({"bidRecommendations": [{"code": "200", "rangeLower": 0.4, "recommended": 1.2, "rangeUpper": 3},
                                           {"code": "404"}]})
    expressions = [{"type": "asinSameAs", "value": "B000000001"}, {"type": "asinSameAs", "value": "B000000002"}]

    rows = live_reads.sd_target_bids(api, ACCOUNT, expressions, "VCPM")

    assert rows[0]["suggested"] == 1.2 and rows[1]["suggested"] is None and "note" in rows[1]
    body = api.calls[0]["json_body"]
    assert body["costType"] == "vcpm" and body["bidOptimization"] == "reach"


def test_category_benchmarks_put_acos_and_ctr_in_percent_with_two_decimals_and_say_when_pages_are_left():
    api = _FakeApi({"brandsAndCategories": [{"brandName": "Acme", "categoryName": "Beauty",
                                             "acos": {"value": 0.480891, "median": 0.28, "top-25pct": 0.2},
                                             "ctr": {"value": 0.0012345},
                                             "roas": {"value": 3.1}}], "nextPageToken": "n"})

    found = live_reads.sb_category_benchmarks(api, ACCOUNT, date(2026, 9, 1),
                                              date(2026, 9, 30), pages=1)

    row = found["rows"][0]
    assert row["acos"]["brand"] == 48.09 and row["acos"]["median"] == 28.0 and row["acos"]["bottom_25"] is None
    assert row["ctr"]["brand"] == 0.12
    assert row["roas"]["brand"] == 3.1
    assert found["more"] is True


def test_invoices_ask_for_plain_json_and_write_days_as_iso():
    api = _FakeApi({"status": "success", "payload": {"invoiceSummaries": [
        {"status": "ACCUMULATING", "fromDate": "20261001", "amountDue": {"amount": 429.25, "currencyCode": "USD"}},
        {"id": "inv-1", "status": "PAID_IN_FULL", "fromDate": "20260901", "toDate": "20260930"}]}})

    invoices = live_reads.invoices(api, ACCOUNT, 500)

    assert invoices[0]["invoice_id"] is None and invoices[0]["period"] == ["2026-10-01", None]
    assert invoices[0]["amount"] == {"amount": 429.25, "currency": "USD"}
    assert invoices[1]["invoice_id"] == "inv-1"
    assert api.calls[0]["accept"] == "application/json"
    assert api.calls[0]["path"] == "/invoices?count=100"


def test_an_invoice_detail_lists_its_lines_by_cost():
    api = _FakeApi({"invoiceSummary": {"id": "inv-1", "status": "PAID_IN_FULL"}, "invoiceLines": [
        {"campaignId": 1, "campaignName": "A", "programName": "SP", "cost": {"amount": 10, "currencyCode": "USD"}},
        {"campaignId": 2, "campaignName": "B", "programName": "SB", "cost": {"amount": 50, "currencyCode": "USD"}}]})

    detail = live_reads.invoice_detail(api, ACCOUNT, "inv/1")

    assert [line["campaign"] for line in detail["lines"]] == ["B", "A"]
    assert api.calls[0]["path"] == "/invoices/inv%2F1"


def test_store_insights_read_numbers_and_iso_days():
    api = _FakeApi({"metricsDetails": [{"date": "20260930", "visits": "703"}]})

    rows = live_reads.store_insights(api, ACCOUNT, "ENTITY1", "VISITS", "DATE", date(2026, 9, 1),
                                     date(2026, 9, 30))

    assert rows == [{"date": "2026-09-30", "visits": 703}]
    assert api.calls[0]["json_body"]["metrics"] == ["VISITS"]


@pytest.mark.parametrize("error, says", [
    (AdsThrottled("x"), "está limitando"),
    (AdsAccessDenied("x", status=403), "no tiene acceso"),
    (oauth.NeedsReauth("x"), "reconectarla en Integraciones"),
    (ConnectionUnavailable("x"), "reconectarla en Integraciones"),
    (AdsApiError("x", status=None), "no respondió a tiempo"),
    (AdsApiError("x", status=503), "HTTP 503"),
    (AdsApiError("x", status=400, body='{"message":"Marketplace is not supported"}'), "no ofrece el uso de presupuesto en MX"),
    (AdsApiError("x", status=422, body='{"details":"bad <b>value</b> see https://a.b/c"}'), "bad value see"),
])
def test_every_failure_reads_as_one_sentence_for_the_account_manager(error, says):
    api = _FakeApi(error)

    with pytest.raises(LiveReadError, match=says) as raised:
        live_reads.budget_usage(api, ACCOUNT, "SP", ["c1"])

    assert isinstance(raised.value, ValueError)


def test_remembered_fetches_once_within_its_ttl_and_never_keeps_a_failure():
    calls = []

    def fetch():
        calls.append(1)
        return ["ok"]

    def failing():
        raise LiveReadError("limitado")

    key = ("test", "remembered")
    live_reads._remembered.pop(key, None)
    first, _ = live_reads.remembered(key, fetch)
    second, _ = live_reads.remembered(key, fetch)
    with pytest.raises(LiveReadError):
        live_reads.remembered(("test", "failing"), failing)

    assert first == second == ["ok"] and len(calls) == 1
    assert ("test", "failing") not in live_reads._remembered


def test_live_reads_exist_only_with_the_token_role_and_the_sealing_key(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "http://rest-gateway")
    monkeypatch.delenv(live_reads.TOKENS_JWT_ENV, raising=False)
    monkeypatch.delenv("INTEGRATIONS_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("INTEGRATIONS_KEY_FILE", str(tmp_path / "missing.pem"))
    assert not live_reads.configured()

    monkeypatch.setenv(live_reads.TOKENS_JWT_ENV, "jwt")
    assert not live_reads.configured()

    (tmp_path / "key.pem").write_text("key")
    monkeypatch.setenv("INTEGRATIONS_KEY_FILE", str(tmp_path / "key.pem"))
    assert live_reads.configured()

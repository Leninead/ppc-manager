"""The live_* MCP tools: what each joins from Amazon and the app, how partial failures read, and when they exist."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from core.amazon_ads import live_reads
from core.amazon_ads.live_reads import LiveReadError
from services.mcp_server import server
from services.mcp_server.limits import Page
from services.mcp_server.tools import amazon_live

CATALOG_CSV = (
    "ad_product,campaign_id,name,state,portfolio_id,portfolio_name,budget_amount,budget_type\n"
    "SP,c1,Fajas Exact,ENABLED,,,50,DAILY\n"
    "SP,c2,Fajas Broad,ENABLED,,,20,DAILY\n"
    "SB,c3,Marca Video,ENABLED,,,30,DAILY\n"
    "SD,c4,Retargeting,ENABLED,,,10,DAILY\n"
    "SP,c5,Vieja,PAUSED,,,5,DAILY\n"
).encode()


class _FakeRest:
    def __init__(self, *, connection_id=1, targets=(), product_ads=(), portfolios=(), cost_type="CPC"):
        self.connection_id = connection_id
        self.targets = list(targets)
        self.product_ads = list(product_ads)
        self.portfolios = list(portfolios)
        self.cost_type = cost_type

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [{"profile_id": "111", "connection_id": self.connection_id, "region": "NA", "country_code": "MX",
                     "currency_code": "MXN", "cliente": "Acme", "account_name": "Acme"}]
        if table == "ads_target":
            return self.targets
        if table == "ads_product_ad":
            return self.product_ads
        if table == "ads_portfolios":
            return self.portfolios
        if table == "ads_ad_group":
            return [{"ad_group_id": "g1", "default_bid": 0.75}]
        if table == "ads_sb_sd_campaign":
            return [{"cost_type": self.cost_type}]
        return []

    def rpc_csv(self, name, args, **_):
        assert name == "campaign_catalog"
        return CATALOG_CSV


@pytest.fixture(autouse=True)
def _no_amazon(monkeypatch):
    """No test reaches Amazon: the client is a token and every read a fake set by the test."""
    monkeypatch.setattr(live_reads, "client_for", lambda account: "api")
    monkeypatch.setattr(amazon_live, "_spending_campaigns", lambda rest, live, chosen: (chosen, ""))
    live_reads._remembered.clear()


def _recommendation(missed_high, share=100.0):
    return {"suggested_budget": 80, "time_in_budget_pct": share, "missed_sales": [missed_high / 3, missed_high],
            "missed_clicks": [1, 3], "missed_impressions": None, "window": None, "rule_increase_pct": None}


def _budget_reads(monkeypatch, *, usage_fails=False, recommendations_fail=False):
    def recommendations(api, live, code, ids):
        if recommendations_fail:
            raise LiveReadError("Amazon está limitando las consultas de las recomendaciones de presupuesto.")
        table = {"c1": _recommendation(300, 60.0), "c2": _recommendation(0), "c3": None, "c4": _recommendation(90, 80)}
        return {campaign_id: table[campaign_id] for campaign_id in ids}

    def usage(api, live, kind, ids):
        if usage_fails:
            raise LiveReadError("Amazon no respondió a tiempo al pedir el uso de presupuesto.")
        table = {"c1": 40.0, "c2": 101.0, "c3": 10.0, "c4": 5.0, "p1": 20.0}
        return {entity_id: {"budget": 50, "usage_pct": table.get(entity_id), "updated_at": "now"} for entity_id in ids}

    monkeypatch.setattr(live_reads, "budget_recommendations", recommendations)
    monkeypatch.setattr(live_reads, "budget_usage", usage)
    monkeypatch.setattr(live_reads, "budget_rules", lambda api, live, code: [{"rule_id": "r1", "state": "ACTIVE"}]
                        if code == "SP" else [])


def test_live_budget_joins_amazon_recommendation_and_usage_by_campaign_and_orders_by_missed_sales(monkeypatch):
    _budget_reads(monkeypatch)

    payload = amazon_live.live_budget(_FakeRest(portfolios=[{"portfolio_id": "p1", "name": "Marca",
                                                             "state": "ENABLED"}]), profile_id="111")

    assert [row["campaign_id"] for row in payload["rows"]] == ["c1", "c4", "c2", "c3"]
    first = payload["rows"][0]
    assert first["campaign"] == "Fajas Exact" and first["time_in_budget_pct"] == 60.0 and first["usage_pct_now"] == 40
    assert payload["rows"][-1]["recommendation"] == "sin recomendación"
    assert payload["counts"] == {"campaigns": 4, "limited_last_7_days": 2, "at_or_over_budget_now": 1,
                                 "limited_last_7_days_or_now": 3, "without_recommendation": 1,
                                 "budget_rules_active": 1}
    assert payload["totals"]["missed_sales"] == [130.0, 390.0]
    assert payload["portfolios"][0]["portfolio"] == "Marca"
    assert payload["account"] == "Acme · MX" and payload["source"] == "Amazon Ads, en vivo"
    assert "errors" not in payload


def test_live_budget_only_limited_keeps_the_campaigns_short_of_budget_now_or_in_the_last_week(monkeypatch):
    _budget_reads(monkeypatch)

    payload = amazon_live.live_budget(_FakeRest(), profile_id="111", only_limited=True)

    assert {row["campaign_id"] for row in payload["rows"]} == {"c1", "c2", "c4"}
    assert payload["total"] == payload["counts"]["limited_last_7_days_or_now"] == 3


def test_a_paged_limited_list_names_what_its_total_counts(monkeypatch):
    _budget_reads(monkeypatch)
    monkeypatch.setattr(amazon_live, "page", lambda rows, offset=0: Page(rows=rows[:1], total=len(rows), offset=0))

    payload = amazon_live.live_budget(_FakeRest(), profile_id="111", only_limited=True)

    assert "Hay 3 campañas que se quedaron sin presupuesto en sus últimos 7 días o ya gastaron el de hoy" \
        in payload["note"]


def test_a_part_amazon_did_not_answer_goes_to_errors_and_the_rest_still_answers(monkeypatch):
    _budget_reads(monkeypatch, usage_fails=True)

    payload = amazon_live.live_budget(_FakeRest(), profile_id="111", product="SP")

    assert payload["rows"][0]["time_in_budget_pct"] == 60.0 and payload["rows"][0]["usage_pct_now"] is None
    assert payload["errors"] == [{"part": "uso SP 0",
                                  "error": "Amazon no respondió a tiempo al pedir el uso de presupuesto."}]


def test_when_every_part_fails_the_first_sentence_is_the_answer(monkeypatch):
    _budget_reads(monkeypatch, usage_fails=True, recommendations_fail=True)
    monkeypatch.setattr(live_reads, "budget_rules", lambda *args: (_ for _ in ()).throw(LiveReadError("sin reglas")))

    with pytest.raises(ValueError, match="limitando"):
        amazon_live.live_budget(_FakeRest(), profile_id="111", product="SP")


def test_campaigns_of_a_batch_that_failed_are_unknown_not_without_recommendation(monkeypatch):
    _budget_reads(monkeypatch, recommendations_fail=True)

    payload = amazon_live.live_budget(_FakeRest(), profile_id="111", product="SP")

    assert all("recommendation" not in row and "time_in_budget_pct" not in row for row in payload["rows"])
    assert payload["counts"]["without_recommendation"] == 0


def test_the_whole_account_reads_only_the_campaigns_that_spent_most_spent_first(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(amazon_live, "campaign_profile", lambda rest, profile_id: SimpleNamespace(
        data_from=date(2026, 9, 1), data_through=date(2026, 9, 30)))
    monkeypatch.setattr(amazon_live, "window_totals", lambda rest, view, start, end: pd.DataFrame(
        {"campaign_id": ["c1", "c2", "c4", "c4"], "spend": [5.0, 0.0, 2.0, 9.0]}))
    catalog = pd.DataFrame({"campaign_id": ["c1", "c2", "c3", "c4"], "product": ["SP", "SP", "SB", "SD"]})

    chosen, note = amazon_live._spending_campaigns(object(), SimpleNamespace(profile_id="111"), catalog)

    assert list(chosen["campaign_id"]) == ["c4", "c1"]
    assert "del 2026-09-24 al 2026-09-30, de 4 habilitadas" in note


def test_an_account_without_an_amazon_ads_authorization_asks_to_connect_it():
    with pytest.raises(ValueError, match="conectarla en Integraciones"):
        amazon_live.live_budget(_FakeRest(connection_id=None), profile_id="111")


def test_live_products_reads_the_advertised_asins_of_enabled_campaigns_and_lists_problems_first(monkeypatch):
    seen = []

    def metadata(api, live, asins):
        seen.extend(asins)
        return [{"asin": "B1", "availability": "IN_STOCK", "eligibility": "ELIGIBLE"},
                {"asin": "B2", "availability": "OUT_OF_STOCK", "eligibility": "ELIGIBLE"}]

    monkeypatch.setattr(live_reads, "product_metadata", metadata)
    rest = _FakeRest(product_ads=[{"asin": "b1", "campaign_id": "c1"}, {"asin": "B2", "campaign_id": "c2"},
                                  {"asin": "B9", "campaign_id": "c5"}, {"asin": "B3", "campaign_id": "c1"}])

    payload = amazon_live.live_products(rest, profile_id="111")

    assert seen == ["B1", "B2", "B3"]
    assert [row["asin"] for row in payload["rows"]] == ["B2", "B1"]
    assert payload["counts"]["with_problems"] == 1 and payload["counts"]["not_found"] == 1
    assert payload["counts"]["by_availability"] == {"IN_STOCK": 1, "OUT_OF_STOCK": 1}
    assert "not_found_note" in payload


def test_live_change_history_names_each_event_campaign_and_pages_by_amazon_offset(monkeypatch):
    asked = {}

    def history(api, live, **kwargs):
        asked.update(kwargs)
        return {"events": [{"at": "2026-10-01T10:00+00:00", "entity": "KEYWORD", "entity_id": "k1",
                            "change": "BID_AMOUNT", "before": 1, "after": 2, "detail": {"campaignId": "c1"}}],
                "total": 120}

    monkeypatch.setattr(live_reads, "change_history", history)

    payload = amazon_live.live_change_history(_FakeRest(), profile_id="111", days=200, entity="keyword",
                                              change="BID_AMOUNT", campaign="Fajas Exact", offset=50)

    assert asked["entities"] == ("KEYWORD",) and asked["campaign_ids"] == ("c1",) and asked["offset"] == 50
    assert payload["rows"][0]["campaign"] == "Fajas Exact"
    assert payload["days"] == 89 and payload["total"] == 120
    assert "offset=51" in payload["note"]


def test_live_keyword_bids_in_sponsored_products_joins_share_and_bids_and_reuses_amazons_answer(monkeypatch):
    calls = {"keywords": 0, "targets": 0}

    def keywords(api, live, campaign_id, ad_group_id, sent):
        calls["keywords"] += 1
        return [{"keyword": "fajas", "targeted": True, "impression_share_pct": 12.5, "impression_rank": 3,
                 "suggested_bids": {"EXACT": {"low": 1, "suggested": 1.2, "high": 1.5}}},
                {"keyword": "faja colombiana", "targeted": False, "impression_share_pct": None,
                 "impression_rank": 2, "suggested_bids": {}}]

    def bids(api, live, campaign_id, ad_group_id, expressions):
        calls["targets"] += 1
        return [{"type": "PAT_ASIN", "value": "B000000001", "low": 0.5, "suggested": 0.7, "high": 0.9}]

    monkeypatch.setattr(live_reads, "sp_keyword_recommendations", keywords)
    monkeypatch.setattr(live_reads, "sp_bid_recommendations", bids)
    rest = _FakeRest(targets=[
        {"ad_group_id": "g1", "target_kind": "keyword", "target_text": "fajas", "match_type": "EXACT", "bid": None},
        {"ad_group_id": "g1", "target_kind": "product", "target_text": 'asin="B000000001"', "bid": 0.6},
        {"ad_group_id": "g1", "target_kind": "product", "target_text": 'asin-expanded-from="B000000001"'},
        {"ad_group_id": "g2", "target_kind": "keyword", "target_text": "otra", "match_type": "BROAD"}])

    first = amazon_live.live_keyword_bids(rest, profile_id="111", campaign="Fajas Exact")
    amazon_live.live_keyword_bids(rest, profile_id="111", campaign="c1")

    assert calls == {"keywords": 1, "targets": 1}
    keyword, product = first["rows"]
    assert keyword["bid"] == 0.75 and keyword["impression_share_pct"] == 12.5 and keyword["suggested"]["suggested"] == 1.2
    assert product["suggested"] == {"low": 0.5, "suggested": 0.7, "high": 0.9}
    assert first["keyword_ideas"][0]["keyword"] == "faja colombiana"
    assert first["not_priced"]["count"] == 1 and first["other_ad_groups"] == ["g2"]


def test_live_keyword_bids_in_brands_and_display(monkeypatch):
    monkeypatch.setattr(live_reads, "sb_keyword_insights", lambda api, live, keywords: [
        {"keyword": "acme", "match": "EXACT", "impression_share_pct": 90.0, "impression_rank": 1, "alerts": []}])
    monkeypatch.setattr(live_reads, "sb_keyword_bids", lambda api, live, campaign_id, keywords: [
        {"keyword": "acme", "match": "EXACT", "low": 1, "suggested": 1.4, "high": 2}])
    monkeypatch.setattr(live_reads, "sd_target_bids", lambda api, live, expressions, cost_type: [
        {"type": "asinSameAs", "value": "B000000002", "low": 0.3, "suggested": 1.1, "high": 2.0}])
    brands = _FakeRest(targets=[{"ad_group_id": "s1", "target_kind": "keyword", "target_text": "acme",
                                 "match_type": "EXACT", "bid": 1.0}])
    display = _FakeRest(cost_type="VCPM", targets=[
        {"ad_group_id": "d1", "target_kind": "product", "target_text": 'asin="B000000002"', "bid": 2},
        {"ad_group_id": "d1", "target_kind": "audience", "target_text": "views=(exact-product lookback=30)"}])

    sb = amazon_live.live_keyword_bids(brands, profile_id="111", campaign="Marca Video")
    sd = amazon_live.live_keyword_bids(display, profile_id="111", campaign="c4")

    assert sb["rows"][0]["impression_share_pct"] == 90.0 and sb["rows"][0]["suggested"]["suggested"] == 1.4
    assert sd["rows"][0]["suggested"]["suggested"] == 1.1 and sd["cost_type"] == "VCPM"
    assert sd["not_priced"]["count"] == 1


def test_live_keyword_bids_needs_one_campaign():
    with pytest.raises(ValueError, match="coincide con 2 campañas"):
        amazon_live.live_keyword_bids(_FakeRest(), profile_id="111", campaign="fajas")


def test_an_invoice_detail_adds_its_cost_by_program(monkeypatch):
    monkeypatch.setattr(live_reads, "invoice_detail", lambda api, live, invoice_id: {
        "invoice": {"invoice_id": invoice_id}, "lines": [
            {"program": "SP", "cost": {"amount": 10.0, "currency": "USD"}},
            {"program": "SB", "cost": {"amount": 30.0, "currency": "USD"}},
            {"program": "SP", "cost": {"amount": 5.0, "currency": "USD"}}]})

    payload = amazon_live.live_invoices(_FakeRest(), profile_id="111", invoice_id="inv-1")

    assert payload["cost_by_program"] == [{"program": "SB", "cost": 30.0, "currency": "USD"},
                                          {"program": "SP", "cost": 15.0, "currency": "USD"}]


def test_live_store_says_when_the_account_has_no_store(monkeypatch):
    monkeypatch.setattr(live_reads, "stores", lambda api, live: [])

    payload = amazon_live.live_store(_FakeRest(), profile_id="111")

    assert payload["rows"] == [] and "no tiene Stores" in payload["note"]


def test_live_store_reads_the_store_named(monkeypatch):
    asked = {}
    monkeypatch.setattr(live_reads, "stores", lambda api, live: [
        {"name": "Acme", "brand_entity_id": "E1"}, {"name": "Acme Kids", "brand_entity_id": "E2"}])

    def insights(api, live, entity, metric, dimension, start, end):
        asked.update(entity=entity, metric=metric)
        return [{"date": "2026-09-30", "sales": 10}]

    monkeypatch.setattr(live_reads, "store_insights", insights)

    payload = amazon_live.live_store(_FakeRest(), profile_id="111", metrics=["SALES"], store="kids")

    assert asked == {"entity": "E2", "metric": "SALES"} and payload["store"] == "Acme Kids"


def test_live_store_reads_several_metrics_at_once_as_one_row_per_day_and_reports_the_one_that_failed(monkeypatch):
    monkeypatch.setattr(live_reads, "stores", lambda api, live: [{"name": "Acme", "brand_entity_id": "E1"}])

    def insights(api, live, entity, metric, dimension, start, end):
        if metric == "ORDERS":
            raise LiveReadError("Amazon está limitando las consultas de las métricas de la Store en esta cuenta.")
        values = {"VISITS": (3, 5), "NEW_TO_STORE": (1, 2)}[metric]
        return [{"date": day, metric.lower(): value} for day, value in zip(("2026-09-30", "2026-09-29"), values)]

    monkeypatch.setattr(live_reads, "store_insights", insights)

    payload = amazon_live.live_store(_FakeRest(), profile_id="111", metrics=["VISITS", "NEW_TO_STORE", "ORDERS"])

    assert payload["rows"] == [{"date": "2026-09-29", "visits": 5, "new_to_store": 2},
                               {"date": "2026-09-30", "visits": 3, "new_to_store": 1}]
    assert payload["metrics"] == ["VISITS", "NEW_TO_STORE", "ORDERS"]
    assert [error["part"] for error in payload["errors"]] == ["ORDERS"]


def test_live_store_without_metrics_reads_them_all(monkeypatch):
    asked = []
    monkeypatch.setattr(live_reads, "stores", lambda api, live: [{"name": "Acme", "brand_entity_id": "E1"}])
    monkeypatch.setattr(live_reads, "store_insights", lambda api, live, entity, metric, *args: asked.append(metric) or [])

    payload = amazon_live.live_store(_FakeRest(), profile_id="111")

    assert sorted(asked) == sorted(live_reads.STORE_METRICS) and payload["metrics"] == list(live_reads.STORE_METRICS)


def test_live_store_prefers_the_exact_name_over_a_longer_one_listed_first(monkeypatch):
    monkeypatch.setattr(live_reads, "stores", lambda api, live: [
        {"name": "EMPETUA By Shapermint", "brand_entity_id": "E1"}, {"name": "Shapermint", "brand_entity_id": "E2"}])
    monkeypatch.setattr(live_reads, "store_insights", lambda api, live, entity, *args: [{"entity": entity}])

    payload = amazon_live.live_store(_FakeRest(), profile_id="111", store="shapermint")

    assert payload["store"] == "Shapermint" and payload["rows"] == [{"entity": "E2"}]


def test_live_store_names_the_stores_when_none_has_the_asked_name(monkeypatch):
    monkeypatch.setattr(live_reads, "stores", lambda api, live: [{"name": "Acme", "brand_entity_id": "E1"}])

    with pytest.raises(ValueError, match="no tiene una Store llamada «Zeta». Las que tiene son «Acme»"):
        amazon_live.live_store(_FakeRest(), profile_id="111", store="Zeta")


def test_the_server_offers_the_live_tools_only_when_it_can_open_the_tokens(monkeypatch):
    monkeypatch.setattr(amazon_live, "available", lambda: False)
    assert not [tool for tool in server.build_tools(object()) if tool["name"].startswith("live_")]

    monkeypatch.setattr(amazon_live, "available", lambda: True)
    live = {tool["name"]: tool["description"] for tool in server.build_tools(object())
            if tool["name"].startswith("live_")}

    assert set(live) == {"live_budget", "live_products", "live_change_history", "live_keyword_bids",
                         "live_category_benchmark", "live_invoices", "live_store"}
    assert all("en vivo" in description and "account" in description for description in live.values())
    assert not any(word in name for name in live for word in ("create", "update", "delete", "request", "save",
                                                              "write"))

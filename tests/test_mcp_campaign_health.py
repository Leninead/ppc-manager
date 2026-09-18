"""campaign_health: the campaigns of an account as Bulk Campañas classifies them, for the chat.

It must see what `breakdown` cannot (campaigns without a single click), classify exactly like the page, and
read its window from the campaign sync rather than from the search-term one.
"""
import csv
import io
import json

import pytest

from services.mcp_server.tools import amazon_ads

RPC_HEADER = ["campaign_id", "name", "state", "targeting_type", "start_date", "budget_amount", "budget_type",
              "bidding_strategy", "portfolio_id", "portfolio_name", "impressions", "clicks", "cost",
              "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "currency_code",
              "budget_capped_days", "days_with_impressions", "top_of_search_is"]


def _campaign(campaign_id, name, *, impressions=1000, clicks=20, cost=10.0, orders=2, sales=100.0, state="ENABLED",
              capped=0, share="25.0", start="2026-03-01"):
    return {"campaign_id": campaign_id, "name": name, "state": state, "targeting_type": "MANUAL",
            "start_date": start, "budget_amount": "30", "budget_type": "DAILY", "bidding_strategy": "MANUAL",
            "portfolio_id": "", "portfolio_name": "", "impressions": str(impressions), "clicks": str(clicks),
            "cost": str(cost), "purchases_7d": str(orders), "sales_7d": str(sales), "purchases_14d": str(orders),
            "sales_14d": str(sales), "currency_code": "USD", "budget_capped_days": str(capped),
            "days_with_impressions": "7", "top_of_search_is": share}


CAMPAIGNS = [
    _campaign("1", "Ghost", impressions=0, clicks=0, cost=0.0, orders=0, sales=0.0),
    _campaign("2", "Bleeder", cost=25.0, orders=0, sales=0.0, share="3.0"),
    _campaign("3", "Winner", cost=10.0, orders=4, sales=100.0, capped=5),
    _campaign("4", "Paused one", state="PAUSED", cost=90.0, orders=0, sales=0.0),
]


PRODUCT_HEADER = ["ad_product", "campaign_id", "name", "state", "start_date", "budget_amount", "budget_type",
                  "cost_type", "portfolio_id", "portfolio_name", "is_multi_ad_groups", "bid_strategy", "metrics_known",
                  "impressions", "clicks", "cost", "purchases", "sales", "purchases_clicks", "sales_clicks",
                  "viewable_impressions", "currency_code"]
TARGET_HEADER = ["ad_product", "target_id", "campaign_id", "campaign_name", "ad_group_id", "target_kind",
                 "target_text", "match_type", "bid", "impressions"]


def _product_campaign(ad_product, campaign_id, name, *, cost=12.0, sales=60.0, sales_clicks=30.0, orders=3,
                      orders_clicks=1, known="t", strategy=""):
    return {"ad_product": ad_product, "campaign_id": campaign_id, "name": name, "state": "ENABLED",
            "start_date": "2026-01-10", "budget_amount": "20", "budget_type": "DAILY", "cost_type": "CPC",
            "portfolio_id": "", "portfolio_name": "", "is_multi_ad_groups": "t" if known == "t" else "f",
            "bid_strategy": strategy, "metrics_known": known, "impressions": "700", "clicks": "14",
            "cost": str(cost), "purchases": str(orders), "sales": str(sales), "purchases_clicks": str(orders_clicks),
            "sales_clicks": str(sales_clicks), "viewable_impressions": "0", "currency_code": "USD"}


def _target(target_id, text, *, ad_product="SP", impressions="0"):
    return {"ad_product": ad_product, "target_id": target_id, "campaign_id": "3", "campaign_name": "Winner",
            "ad_group_id": "31", "target_kind": "keyword", "target_text": text, "match_type": "EXACT",
            "bid": "0.75", "impressions": impressions}


def _csv(header, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class FakeRest:
    def __init__(self, campaigns=CAMPAIGNS, *, completed=True, settings=None, products=(), targets=()):
        self.campaigns = list(campaigns)
        # SB / SD campaigns and targets (migration 015): none unless a test gives them.
        self.products = list(products)
        self.targets = list(targets)
        self.reads = []
        self.profiles = [{"profile_id": "111", "account_id": 1, "cliente": "dermaglos", "account_name": "Dermaglos",
                          "country_code": "US", "currency_code": "USD", "account_type": "seller",
                          "timezone": "America/Los_Angeles", "status": "active", "data_from": "2026-07-11",
                          "data_through": "2026-09-14", "refreshed_on": "2026-09-15",
                          "last_success_at": "2026-09-15T10:00:00+00:00", "last_error": ""}]
        self.jobs = [{"id": 441, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns",
                      "trigger": "scheduled_daily", "external_account_id": "111", "status": "completed",
                      "window_start": "2026-07-14", "window_end": "2026-09-16", "local_day": "2026-09-17",
                      "finished_at": "2026-09-18T00:51:00+00:00", "created_at": "2026-09-18T00:43:00+00:00"}
                     ] if completed else []
        self.settings = [{"module": "bulk_campaigns", "subject_id": "111", "params": settings,
                          "updated_by": "ana", "updated_at": "2026-09-17T12:00:00+00:00"}] if settings else []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [dict(row) for row in self.profiles]
        if table == "integration_sync_jobs":
            return [dict(job) for job in self.jobs if params.get("job_kind") == f"eq.{job['job_kind']}"
                    and params.get("status", "eq.completed") == f"eq.{job['status']}"][:1]
        if table == "ai_analysis_settings":
            return [dict(row) for row in self.settings]
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, **_):
        if name == "product_campaigns_between":
            return _csv(PRODUCT_HEADER, self.products) if self.products else b""
        if name == "graduation_targets_between":
            return _csv(TARGET_HEADER, self.targets) if self.targets else b""
        assert name == "campaigns_between"
        self.reads.append((args["p_from"], args["p_to"]))
        return _csv(RPC_HEADER, self.campaigns)


def _health(rest=None, **options):
    return amazon_ads.campaign_health(rest or FakeRest(), profile_id="111", **options)


def test_campaigns_without_a_single_click_are_there_with_their_diagnosis():
    rows = {row["campaign"]: row for row in _health()["rows"]}

    assert rows["Ghost"]["diagnosis"] == "FANTASMA"
    assert (rows["Bleeder"]["diagnosis"], rows["Winner"]["diagnosis"]) == ("PAUSAR", "ESCALAR")
    assert "Paused one" not in rows


def test_the_window_comes_from_the_campaign_sync_not_from_the_search_term_one():
    rest = FakeRest()

    payload = _health(rest)

    # The search-term sync ends on the 14th; the campaign sync on the 16th.
    assert payload["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}
    assert rest.reads == [("2026-09-10", "2026-09-16")]
    assert payload["provisional_days"] == ["2026-09-15", "2026-09-16"]


def test_a_filter_narrows_the_rows_but_the_counts_and_totals_cover_every_enabled_campaign():
    payload = _health(diagnosis="PAUSAR")

    assert [row["campaign"] for row in payload["rows"]] == ["Bleeder"]
    assert payload["counts"] == {"FANTASMA": 1, "PAUSAR": 1, "ESCALAR": 1}
    assert payload["totals"]["spend"] == 35.0
    assert payload["pause_spend"] == 25.0


def test_the_signals_travel_as_a_list_and_filter_too():
    payload = _health(signal="Limitada por presupuesto")

    assert [row["campaign"] for row in payload["rows"]] == ["Winner"]
    assert payload["rows"][0]["signals"] == ["Limitada por presupuesto"]
    assert {row["campaign"]: row["signals"] for row in _health()["rows"]}["Bleeder"] == ["Baja visibilidad"]


def test_it_classifies_with_the_account_parameters_and_says_where_they_came_from():
    default = _health()
    strict = _health(FakeRest(settings={"target_acos": 35, "spend_to_pause": 30, "min_orders_to_scale": 2}))

    assert default["parameters"]["origin"] == "los de siempre de Bulk Campañas"
    assert strict["parameters"]["origin"] == "guardados de la cuenta en Bulk Campañas"
    # 25 of spend without orders is under a 30 threshold: no longer a pause.
    assert {row["campaign"]: row["diagnosis"] for row in strict["rows"]}["Bleeder"] == "OK"


def test_rows_go_by_spend_and_the_whole_payload_is_plain_json():
    payload = _health()

    assert [row["campaign"] for row in payload["rows"]] == ["Bleeder", "Winner", "Ghost"]
    json.dumps(payload)
    assert payload["rows"][2]["acos"] is None


def test_an_account_the_campaign_sync_never_completed_says_so():
    with pytest.raises(ValueError, match="todavía no tiene campañas sincronizadas"):
        _health(FakeRest(completed=False))


def test_an_unknown_sort_is_refused():
    with pytest.raises(ValueError, match="sort_by"):
        _health(sort_by="roas")


PRODUCTS = [_product_campaign("SB", "701", "Brand Video", strategy="MANUAL"),
            _product_campaign("SD", "801", "Display Views", cost=30.0, sales=0.0, sales_clicks=0.0, orders=0,
                              orders_clicks=0, strategy="conversions")]


def test_sb_and_sd_campaigns_come_with_their_product_and_their_click_only_sales():
    rows = {row["campaign"]: row for row in _health(FakeRest(products=PRODUCTS))["rows"]}

    assert {name: row["product"] for name, row in rows.items()} == {
        "Ghost": "SP", "Bleeder": "SP", "Winner": "SP", "Brand Video": "SB", "Display Views": "SD"}
    assert (rows["Brand Video"]["sales"], rows["Brand Video"]["sales_clicks"]) == (60.0, 30.0)
    assert rows["Winner"]["sales_clicks"] == rows["Winner"]["sales"]
    assert rows["Brand Video"]["bid_strategy"] == "Custom bid adjustments"
    assert (rows["Display Views"]["diagnosis"], rows["Display Views"]["bid_strategy"]) == (
        "PAUSAR", "Optimize for conversions")


def test_an_account_with_only_sp_answers_as_it_always_did():
    row = _health()["rows"][0]

    assert row["product"] == "SP" and "sales_clicks" not in row


def test_a_product_narrows_the_rows_the_counts_and_the_totals():
    payload = _health(FakeRest(products=PRODUCTS), product="SD")

    assert [row["campaign"] for row in payload["rows"]] == ["Display Views"]
    assert payload["counts"] == {"PAUSAR": 1}
    assert payload["totals"]["spend"] == 30.0


def test_old_format_sb_campaigns_without_metrics_stay_out_and_the_answer_says_so():
    rest = FakeRest(products=[PRODUCTS[0], _product_campaign("SB", "702", "Brand Legacy", known="f", cost=0.0)])

    payload = _health(rest)

    assert "Brand Legacy" not in [row["campaign"] for row in payload["rows"]]
    assert payload["old_format_note"].startswith("1 campaña SB del formato anterior todavía no tiene métricas")
    assert "old_format_note" not in _health(rest, product="SD")


def test_an_unknown_product_is_refused():
    with pytest.raises(ValueError, match="product"):
        _health(product="DSP")


def _idle(rest, **options):
    return amazon_ads.idle_targets(rest, profile_id="111", **options)


def test_idle_targets_are_the_ones_without_impressions_counted_by_product():
    rest = FakeRest(targets=[_target("91", "demo idle kw"), _target("92", "busy kw", impressions="40"),
                             _target("93", "sd idle", ad_product="SD")])

    payload = _idle(rest)

    assert [(row["product"], row["target"], row["kind"], row["bid"]) for row in payload["rows"]] == [
        ("SP", "demo idle kw", "Keyword", 0.75), ("SD", "sd idle", "Keyword", 0.75)]
    assert payload["counts"] == {"SD": {"considered": 1, "idle": 1}, "SP": {"considered": 2, "idle": 1}}
    assert payload["window"] == {"from": "2026-09-10", "to": "2026-09-16", "days": 7}
    json.dumps(payload)


def test_idle_targets_of_one_product_count_only_that_product():
    rest = FakeRest(targets=[_target("91", "demo idle kw"), _target("93", "sd idle", ad_product="SD")])

    payload = _idle(rest, product="SD")

    assert [row["target"] for row in payload["rows"]] == ["sd idle"]
    assert payload["counts"] == {"SD": {"considered": 1, "idle": 1}}
    assert "note" not in payload or "Todavía no hay" not in payload["note"]


def test_idle_targets_say_when_nothing_synced_yet():
    payload = _idle(FakeRest())

    assert payload["rows"] == [] and payload["note"] == "Los targets de esta cuenta todavía no se sincronizaron."

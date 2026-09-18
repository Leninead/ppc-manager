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


class FakeRest:
    def __init__(self, campaigns=CAMPAIGNS, *, completed=True, settings=None):
        self.campaigns = list(campaigns)
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
        assert name == "campaigns_between"
        self.reads.append((args["p_from"], args["p_to"]))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=RPC_HEADER)
        writer.writeheader()
        writer.writerows(self.campaigns)
        return buffer.getvalue().encode("utf-8")


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

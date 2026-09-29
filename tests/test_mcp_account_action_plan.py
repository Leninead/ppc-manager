"""account_action_plan: what to do in one account, each action from its own module's rules, in one call."""
from __future__ import annotations

import pytest

from services.mcp_server.tools import account_action_plan as plan_tool

WINDOW = {"from": "2026-09-15", "to": "2026-09-21", "days": 7}
TERMS_WINDOW = {"from": "2026-09-16", "to": "2026-09-22", "days": 7}
BULK_PARAMETERS = {"target_acos": 30, "spend_to_pause": 20.0, "min_orders_to_scale": 3, "origin": "guardados",
                   "rules": {"PAUSAR": "..."}, "signal_rules": {}}


def _campaign(name: str, diagnosis: str, *, spend: float, sales: float, **extra) -> dict:
    return {"campaign": name, "campaign_id": name.lower(), "product": "SP", "diagnosis": diagnosis, "spend": spend,
            "sales": sales, "orders": 1 if sales else 0, "acos": round(spend / sales * 100, 2) if sales else None,
            "daily_budget": 20.0, "signals": [], **extra}


def _health(*, diagnosis: str = "", signal: str = "", **_) -> dict:
    if diagnosis == "PAUSAR":
        rows = [_campaign("Sangra", "PAUSAR", spend=66.0, sales=0.0)]
    elif diagnosis == "FANTASMA":
        rows = [_campaign("Muda", "FANTASMA", spend=0.0, sales=0.0)]
    else:
        rows = [_campaign("Ganadora", "ESCALAR", spend=40.0, sales=400.0, budget_capped_days=5),
                _campaign("Cara", "REVISAR", spend=90.0, sales=100.0, budget_capped_days=6),
                _campaign("Pareja", "OK", spend=30.0, sales=120.0, budget_capped_days=2)]
    return {"rows": rows, "total": len(rows), "window": WINDOW, "currency": "USD",
            "counts": {"PAUSAR": 1, "FANTASMA": 3, "OK": 10}, "pause_spend": 66.0, "parameters": BULK_PARAMETERS}


def _candidates(*, section: str, **_) -> dict:
    if section == "negatives":
        rows = [{"search_term": "gratis", "campaign": "Auto", "spend": 12.0, "clicks": 9, "priority": "Alta",
                 "rule": "R2", "in_bulk": True},
                {"search_term": "marca", "campaign": "Exact", "spend": 30.0, "clicks": 20, "priority": "Alta",
                 "rule": "R3", "in_bulk": False}]
        return {"rows": rows, "total": 2, "window": TERMS_WINDOW, "currency": "USD", "counts": {"in_bulk": 1},
                "totals_in_bulk": {"spend": 12.0, "clicks": 9}, "parameters": {"price": 25.0, "origin": "defecto"}}
    rows = [{"search_term": "crema noche", "campaign": "Broad", "orders": 4, "acos": 20.0, "suggested_bid": 0.9,
             "exact_in_account": "no está"}]
    return {"rows": rows, "total": 1, "window": TERMS_WINDOW, "currency": "USD", "counts": {},
            "parameters": {"price": 25.0, "origin": "defecto"}}


class _Choice:
    profile_id = "279177258676903"
    candidates = ()


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setattr(plan_tool, "choose_account", lambda *args, **kwargs: _Choice())
    monkeypatch.setattr(plan_tool, "campaign_health", lambda rest, **call: _health(**call))
    monkeypatch.setattr(plan_tool, "search_term_candidates", lambda rest, **call: _candidates(**call))
    return lambda: plan_tool.account_action_plan(object(), account="dermaglos")


def _actions(payload: dict) -> dict:
    return {action["action"]: action for action in payload["actions"]}


def test_every_action_comes_with_its_count_its_money_and_its_first_items(plan):
    """Asked what to do tomorrow in an account, the chat made eight calls and three minutes of reasoning."""
    actions = _actions(plan())

    assert actions["pausar_campañas"]["count"] == 1 and actions["pausar_campañas"]["spend"] == 66.0
    assert actions["pausar_campañas"]["items"][0]["campaign"] == "Sangra"
    assert actions["revisar_sin_impresiones"]["count"] == 3
    assert actions["cosechar_en_exact"]["items"][0]["search_term"] == "crema noche"


def test_only_budget_limited_campaigns_that_bulk_would_scale_or_keep_are_worth_more_budget(plan):
    budget = _actions(plan())["subir_presupuesto"]

    assert [item["campaign"] for item in budget["items"]] == ["Ganadora", "Pareja"]
    assert (budget["count"], budget["sales"]) == (2, 520.0)


def test_only_the_negatives_that_go_into_the_bulk_are_proposed(plan):
    negate = _actions(plan())["negativizar"]

    assert [item["search_term"] for item in negate["items"]] == ["gratis"]
    assert (negate["count"], negate["spend"]) == (1, 12.0)


def test_each_module_says_its_own_window_and_parameters_without_the_long_rules(plan):
    payload = plan()

    assert payload["windows"] == {"bulk_campaigns": WINDOW, "search_term_report": TERMS_WINDOW}
    assert payload["parameters"]["bulk_campaigns"] == {"target_acos": 30, "spend_to_pause": 20.0,
                                                       "min_orders_to_scale": 3, "origin": "guardados"}
    assert payload["parameters"]["search_term_report"]["price"] == 25.0


def test_a_source_that_cannot_be_read_costs_its_action_not_the_plan(plan, monkeypatch):
    def no_terms(rest, **call):
        raise ValueError("La cuenta no tuvo búsquedas con clicks en ese período.")

    monkeypatch.setattr(plan_tool, "search_term_candidates", no_terms)

    actions = _actions(plan())

    assert actions["negativizar"] == {"action": "negativizar",
                                      "unavailable": "La cuenta no tuvo búsquedas con clicks en ese período."}
    assert actions["pausar_campañas"]["count"] == 1


def test_an_account_name_that_matches_several_returns_the_candidates(monkeypatch):
    class Several:
        profile_id = ""
        candidates = ({"account": "Marca · US"}, {"account": "Marca · MX"})

        def as_payload(self):
            return {"candidates": list(self.candidates)}

    monkeypatch.setattr(plan_tool, "choose_account", lambda *args, **kwargs: Several())

    assert plan_tool.account_action_plan(object(), account="marca") == {"candidates": list(Several.candidates)}

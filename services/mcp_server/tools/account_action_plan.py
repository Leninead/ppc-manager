"""What to do next in one account: the actions each module's rules find there, side by side in one call.

Asked what to do tomorrow in an account, the chat made eight calls — the Bulk Campañas analysis twice, the negatives,
the structure, Amazon Ads — and three minutes of reasoning to put them next to each other. Here each action comes
from its own module's rules, read live over the window asked, with its count, the money it moves and its first items.
The order of the actions is not a priority: which one comes first is the AM's call, with these figures in front.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from core.amazon_ads.campaign_analyzer import BUDGET_LIMITED
from services.mcp_server.tools.account_resolver import choose_account
from services.mcp_server.tools.amazon_ads import campaign_health
from services.mcp_server.tools.module_results import search_term_candidates
from services.mcp_server.tools.windows import DEFAULT_DAYS

log = logging.getLogger(__name__)

ITEMS_PER_ACTION = 5
# Budget-limited campaigns worth more budget: the ones Bulk Campañas would scale or leave as they are.
WORTH_MORE_BUDGET = ("ESCALAR", "OK")
BUDGET_LIMITED_READ = 50
PLAN_NOTE = ("Cada acción sale de las reglas de su módulo, con sus propios parámetros y su ventana (windows: la de "
             "Bulk Campañas sale de los reportes de campaña y la del Search Term Report de los search terms, que "
             "pueden llegar a días distintos; parameters dice qué valores usó cada uno y de dónde salieron). "
             "El orden de las acciones no es una prioridad: decidí con "
             "sus cifras. count cuenta todas las de la cuenta; items trae las primeras. Una acción con unavailable no "
             "se pudo leer y dice por qué.")

_CAMPAIGN_FIELDS = ("campaign", "campaign_id", "product", "spend", "sales", "orders", "acos")


def account_action_plan(rest, *, profile_id: str = "", account: str = "", days: int = DEFAULT_DAYS,
                        date_from: str = "", date_to: str = "") -> dict:
    """The next actions in one account, from Bulk Campañas and the Search Term Report: campaigns to pause, campaigns
    that sell within target and hit their budget, negatives that go into the bulk, terms to harvest with no exact that
    runs, and enabled campaigns without impressions."""
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    window = {"profile_id": choice.profile_id, "days": days, "date_from": date_from, "date_to": date_to}
    reads = {
        "pause": partial(campaign_health, rest, **window, diagnosis="PAUSAR", limit=ITEMS_PER_ACTION),
        "budget": partial(campaign_health, rest, **window, signal=BUDGET_LIMITED, sort_by="sales",
                          limit=BUDGET_LIMITED_READ),
        "idle": partial(campaign_health, rest, **window, diagnosis="FANTASMA", limit=ITEMS_PER_ACTION),
        "negatives": partial(search_term_candidates, rest, **window, section="negatives", limit=BUDGET_LIMITED_READ),
        "harvest": partial(search_term_candidates, rest, **window, section="harvest", without_running_exact=True,
                           limit=ITEMS_PER_ACTION),
    }
    with ThreadPoolExecutor(max_workers=len(reads), thread_name_prefix="action-plan") as pool:
        submitted = {name: pool.submit(read) for name, read in reads.items()}
        read = {name: _outcome(name, future) for name, future in submitted.items()}

    health = next((read[name] for name in ("pause", "budget", "idle") if "error" not in read[name]), {})
    terms = next((read[name] for name in ("negatives", "harvest") if "error" not in read[name]), {})
    return {
        "profile_id": choice.profile_id,
        "windows": {"bulk_campaigns": health.get("window"), "search_term_report": terms.get("window")},
        "currency": health.get("currency") or terms.get("currency"),
        "actions": [_pause(read["pause"]), _negate(read["negatives"]), _raise_budget(read["budget"]),
                    _harvest(read["harvest"]), _review_idle(read["idle"])],
        "parameters": {"bulk_campaigns": _parameters(health), "search_term_report": _parameters(terms)},
        "note": PLAN_NOTE,
    }


def _outcome(name: str, future) -> dict:
    """What one source answered, or why it could not: a missing source costs its action, never the plan."""
    try:
        return future.result()
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — the other four actions still stand
        log.exception("account_action_plan: %s could not be read", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _pause(payload: dict) -> dict:
    if "error" in payload:
        return _unavailable("pausar_campañas", payload)
    return {"action": "pausar_campañas", "source": "Bulk Campañas: diagnóstico PAUSAR",
            "count": int((payload.get("counts") or {}).get("PAUSAR", 0)), "spend": payload.get("pause_spend"),
            "items": [_pick(row, _CAMPAIGN_FIELDS) for row in payload.get("rows") or []]}


def _raise_budget(payload: dict) -> dict:
    if "error" in payload:
        return _unavailable("subir_presupuesto", payload)
    worth = [row for row in payload.get("rows") or [] if row.get("diagnosis") in WORTH_MORE_BUDGET]
    action = {"action": "subir_presupuesto",
              "source": f"Bulk Campañas: señal «{BUDGET_LIMITED}» en campañas con diagnóstico ESCALAR u OK",
              "count": len(worth), "sales": round(sum(row.get("sales") or 0 for row in worth), 2),
              "items": [_pick(row, (*_CAMPAIGN_FIELDS, "diagnosis", "daily_budget", "budget_capped_days"))
                        for row in worth[:ITEMS_PER_ACTION]]}
    if (payload.get("total") or 0) > BUDGET_LIMITED_READ:
        action["count_note"] = (f"Se miraron las {BUDGET_LIMITED_READ} limitadas por presupuesto que más venden de "
                                f"{payload['total']}: count puede quedar corto.")
    return action


def _review_idle(payload: dict) -> dict:
    if "error" in payload:
        return _unavailable("revisar_sin_impresiones", payload)
    return {"action": "revisar_sin_impresiones", "source": "Bulk Campañas: diagnóstico FANTASMA",
            "count": int((payload.get("counts") or {}).get("FANTASMA", 0)),
            "items": [_pick(row, ("campaign", "campaign_id", "product", "daily_budget"))
                      for row in payload.get("rows") or []]}


def _negate(payload: dict) -> dict:
    if "error" in payload:
        return _unavailable("negativizar", payload)
    in_bulk = [row for row in payload.get("rows") or [] if row.get("in_bulk")]
    return {"action": "negativizar", "source": "Search Term Report: candidatos a negativo que entran al bulk",
            "count": int((payload.get("counts") or {}).get("in_bulk", len(in_bulk))),
            "spend": (payload.get("totals_in_bulk") or {}).get("spend"),
            "items": [_pick(row, ("search_term", "campaign", "spend", "clicks", "priority", "rule"))
                      for row in in_bulk[:ITEMS_PER_ACTION]]}


def _harvest(payload: dict) -> dict:
    if "error" in payload:
        return _unavailable("cosechar_en_exact", payload)
    return {"action": "cosechar_en_exact",
            "source": "Search Term Report: candidatos a harvest sin una exact que corra en la cuenta",
            "count": int(payload.get("total") or 0),
            "items": [_pick(row, ("search_term", "campaign", "orders", "acos", "suggested_bid", "exact_in_account"))
                      for row in payload.get("rows") or []]}


def _unavailable(action: str, payload: dict) -> dict:
    return {"action": action, "unavailable": payload["error"]}


def _parameters(payload: dict) -> dict:
    parameters = payload.get("parameters") or {}
    return {key: value for key, value in parameters.items() if key not in ("rules", "signal_rules")}


def _pick(row: dict, fields: tuple[str, ...]) -> dict:
    return {field: row[field] for field in fields if field in row}

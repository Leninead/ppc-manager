"""all_accounts: a per-account tool answered for every account at once, the lap the chat used to do by hand."""
from __future__ import annotations

import inspect
from functools import partial

import pytest

from services.mcp_server.limits import serialized_chars
from services.mcp_server.tools import all_accounts
from services.mcp_server.tools.all_accounts import MAX_PAYLOAD_CHARS, answers_all_accounts, run_on_all_accounts


def _profile(profile_id: str, client: str, country: str, currency: str, *, synced: bool = True) -> dict:
    return {"profile_id": profile_id, "account_id": 1, "cliente": client, "account_name": f"{client} LLC",
            "country_code": country, "currency_code": currency, "account_type": "seller", "timezone": "",
            "status": "active", "data_from": "2026-08-01", "data_through": "2026-09-21" if synced else None,
            "refreshed_on": "2026-09-22", "last_success_at": "2026-09-22T11:05:00+00:00", "last_error": ""}


PROFILES = [
    _profile("1", "Alfa", "US", "USD"),
    _profile("2", "Beta", "US", "USD"),
    _profile("3", "Gama", "MX", "MXN"),
    _profile("4", "Delta", "US", "USD"),
    _profile("5", "Nueva", "US", "USD", synced=False),
]


class _ProfilesRest:
    def select(self, table, params):
        return [dict(profile) for profile in PROFILES]


def _campaigns(profile_id: str, spends: list[float], currency: str) -> list[dict]:
    return [{"campaign": f"{profile_id}-{index}", "spend": spend} for index, spend in enumerate(spends)]


ACCOUNT_ROWS = {"1": _campaigns("1", [50.0, 10.0], "USD"), "2": _campaigns("2", [80.0, 5.0], "USD"),
                "3": _campaigns("3", [900.0], "MXN"), "4": []}


def _per_account(profile_id: str, offset: int, limit: int, *, page_size: int = 50) -> dict:
    rows = ACCOUNT_ROWS[profile_id]
    currency = "MXN" if profile_id == "3" else "USD"
    return {"rows": rows[offset:offset + min(limit, page_size)], "total": len(rows), "currency": currency,
            "window": {"from": "2026-09-15", "to": "2026-09-21", "days": 7},
            "counts": {"PAUSAR": len(rows), "by_signal": {"capped": 1}, "names": ["x"]},
            "totals": {"spend": sum(row["spend"] for row in rows), "acos": 30.0}}


def _by_spend(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: -row["spend"])


def _run(per_account=_per_account, rows_per_currency: int = 15) -> dict:
    return run_on_all_accounts(_ProfilesRest(), per_account, rank=_by_spend, rows_per_currency=rows_per_currency,
                               what="campañas")


def test_the_rows_of_every_account_come_ranked_together_in_one_list_per_currency():
    """«Which campaigns run out of budget?» opened three accounts one call at a time and ranked them by reasoning."""
    payload = _run()

    usd, mxn = payload["by_currency"]
    assert (usd["currency"], usd["accounts"], usd["total"]) == ("USD", 2, 4)
    assert [(row["account"], row["spend"]) for row in usd["rows"]] == [
        ("Beta · US", 80.0), ("Alfa · US", 50.0), ("Alfa · US", 10.0), ("Beta · US", 5.0)]
    assert usd["rows"][0]["profile_id"] == "2"
    assert (mxn["currency"], [row["spend"] for row in mxn["rows"]]) == ("MXN", [900.0])
    assert payload["total"] == 5


def test_counts_add_up_over_every_account_and_totals_only_what_adds_within_a_currency():
    payload = _run()

    assert payload["counts"] == {"PAUSAR": 5, "by_signal": {"capped": 4}}
    usd = payload["by_currency"][0]
    assert usd["totals"] == {"spend": 145.0}


def test_no_account_is_dropped_silently():
    def per_account(profile_id, offset, limit):
        if profile_id == "4":
            raise ValueError("La cuenta 4 todavía no tiene campañas sincronizadas.")
        if profile_id == "2":
            raise RuntimeError("PostgREST se cayó")
        return _per_account(profile_id, offset, limit)

    accounts = _run(per_account)["accounts"]

    assert accounts["asked"] == 5
    assert [line["account"] for line in accounts["with_rows"]] == ["Alfa · US", "Gama · MX"]
    assert accounts["without_data"] == [
        {"account": "Delta · US", "reason": "La cuenta 4 todavía no tiene campañas sincronizadas."},
        {"account": "Nueva · US", "reason": "Todavía no tiene datos sincronizados."}]
    assert accounts["failed"] == [{"account": "Beta · US", "error": "RuntimeError: PostgREST se cayó"}]


def test_an_account_with_no_matching_rows_is_named_apart_from_the_ones_without_data():
    accounts = _run()["accounts"]

    assert accounts["without_rows"] == ["Delta · US"]


def test_a_page_cut_by_size_is_completed_from_the_next_offset():
    payload = _run(partial(_per_account, page_size=1), rows_per_currency=2)

    assert [row["spend"] for row in payload["by_currency"][0]["rows"]] == [80.0, 50.0]
    assert payload["accounts"]["with_rows"][0] == {"account": "Alfa · US", "profile_id": "1", "rows": 2}


def test_the_windows_say_in_how_many_accounts_each_was_read():
    assert _run()["windows"] == [{"from": "2026-09-15", "to": "2026-09-21", "accounts": 4}]


def test_the_answer_fits_what_the_provider_lets_through_and_every_currency_keeps_its_first_row(monkeypatch):
    fat = {"1": [{"campaign": f"c{i}", "spend": 1000.0 - i, "detail": "x" * 900} for i in range(60)],
           "2": [], "3": [{"campaign": "mx", "spend": 5.0, "detail": "y" * 900}], "4": []}
    monkeypatch.setattr(all_accounts, "MAX_PAYLOAD_CHARS", 12_000)
    monkeypatch.setitem(ACCOUNT_ROWS, "1", fat["1"])
    monkeypatch.setitem(ACCOUNT_ROWS, "2", fat["2"])
    monkeypatch.setitem(ACCOUNT_ROWS, "3", fat["3"])

    payload = _run(rows_per_currency=60)

    assert serialized_chars(payload) <= 12_000
    usd, mxn = payload["by_currency"]
    assert 1 <= usd["showing"] < 60 and "note" in usd
    assert mxn["showing"] == 1


def _tool(rest, *, profile_id: str = "", account: str = "", sort_by: str = "spend", offset: int = 0,
          limit: int = 50) -> dict:
    return _per_account(profile_id, offset, limit)


def test_the_flag_joins_the_signature_the_model_sees_and_keeps_every_other_parameter():
    decorated = answers_all_accounts(what="campañas", rank=lambda rows, call: rows)(_tool)

    parameters = inspect.signature(partial(decorated, object()), eval_str=True).parameters
    assert list(parameters) == ["profile_id", "account", "sort_by", "offset", "limit", "all_accounts"]
    assert parameters["all_accounts"].annotation is bool and parameters["all_accounts"].default is False


def test_without_the_flag_the_tool_reads_one_account_as_before():
    decorated = answers_all_accounts(what="campañas", rank=lambda rows, call: rows)(_tool)

    assert decorated(_ProfilesRest(), profile_id="3")["rows"] == [{"campaign": "3-0", "spend": 900.0}]


def test_the_rank_gets_the_arguments_of_the_call():
    seen = []

    def rank(rows, call):
        seen.append(call)
        return rows

    answers_all_accounts(what="campañas", rank=rank)(_tool)(_ProfilesRest(), all_accounts=True, sort_by="sales")

    assert seen and all(call == {"sort_by": "sales"} for call in seen)


@pytest.mark.parametrize("call, message", [
    ({"profile_id": "1"}, "sin profile_id ni account"),
    ({"account": "alfa"}, "sin profile_id ni account"),
    ({"offset": 200}, "hasta la fila 200"),
])
def test_all_accounts_refuses_what_only_makes_sense_for_one_account(call, message):
    decorated = answers_all_accounts(what="campañas", rank=lambda rows, arguments: rows)(_tool)

    with pytest.raises(ValueError, match=message):
        decorated(_ProfilesRest(), all_accounts=True, **call)


def _ranked_by_spend(rows, call):
    return _by_spend(rows)


def test_offset_brings_the_next_page_of_every_currency():
    """The chat paged the third negative of the bulk with offset=7 and got a bare error, so nobody found it."""
    decorated = answers_all_accounts(what="campañas", rank=_ranked_by_spend)(_tool)

    first = decorated(_ProfilesRest(), all_accounts=True, limit=2)
    second = decorated(_ProfilesRest(), all_accounts=True, limit=2, offset=2)

    assert [row["spend"] for row in first["by_currency"][0]["rows"]] == [80.0, 50.0]
    assert [row["spend"] for row in second["by_currency"][0]["rows"]] == [10.0, 5.0]
    assert second["by_currency"][0]["offset"] == 2
    assert second["by_currency"][1]["rows"] == []
    assert "desde la fila 3" in second["note"]


def test_each_currency_says_where_its_next_page_starts():
    decorated = answers_all_accounts(what="campañas", rank=_ranked_by_spend)(_tool)

    usd, mxn = decorated(_ProfilesRest(), all_accounts=True, limit=2)["by_currency"]

    assert usd["next_offset"] == 2 and "offset=2" in usd["note"]
    assert "next_offset" not in mxn and "note" not in mxn


def test_a_page_asks_every_account_for_the_rows_up_to_its_end():
    asked = []

    def per_account(profile_id, offset, limit):
        asked.append((profile_id, offset, limit))
        return _per_account(profile_id, offset, limit)

    run_on_all_accounts(_ProfilesRest(), per_account, rank=_by_spend, rows_per_currency=2, what="campañas",
                        offset=2)

    assert ("1", 0, 4) in asked and ("3", 0, 4) in asked


def test_the_last_page_stops_at_the_row_limit():
    asked = []

    def spy(rest, *, profile_id: str = "", account: str = "", sort_by: str = "spend", offset: int = 0,
            limit: int = 50) -> dict:
        asked.append(offset + limit)
        return _per_account(profile_id, offset, limit)

    answers_all_accounts(what="campañas", rank=_ranked_by_spend)(spy)(_ProfilesRest(), all_accounts=True,
                                                                      offset=190, limit=50)

    assert max(asked) == 200


def test_the_payload_limit_stays_under_the_providers_cut():
    assert MAX_PAYLOAD_CHARS < 20_000

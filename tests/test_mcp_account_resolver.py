"""account=: a tool reads the account a question names, by its id or by part of its name."""
from __future__ import annotations

import pytest

from services.mcp_server.tools.account_resolver import choose_account, name_key

JOB = {"id": 1, "integration_slug": "amazon_ads", "job_kind": "sp_campaigns", "trigger": "scheduled_daily",
       "status": "completed", "window_start": "2026-09-10", "window_end": "2026-09-16", "local_day": "2026-09-17",
       "finished_at": "2026-09-17T11:05:00+00:00", "created_at": "2026-09-17T10:43:00+00:00"}


def _profile(profile_id: str, cliente: str, country: str) -> dict:
    return {"profile_id": profile_id, "account_id": 1, "cliente": cliente, "account_name": cliente,
            "country_code": country, "currency_code": "USD", "account_type": "seller", "timezone": "",
            "status": "active", "data_from": "2026-08-01", "data_through": "2026-09-16", "refreshed_on": "2026-09-17",
            "last_success_at": "2026-09-17T11:05:00+00:00", "last_error": ""}


class _FakeRest:
    def __init__(self, spend_by_profile: dict[str, float]):
        self.profiles = [_profile("1", "Dermaglós", "US"), _profile("2", "Dermaglós", "MX"),
                         _profile("3", "Acme", "US"), _profile("4", "Acme Pro", "US")]
        self.spend_by_profile = spend_by_profile
        self.reads: list[str] = []

    def select(self, table, params):
        if table == "integration_sync_jobs":
            return [{**JOB, "external_account_id": params["external_account_id"].removeprefix("eq.")}]
        return list(self.profiles)

    def rpc(self, name, args, **_):
        assert name == "campaign_daily_totals"
        self.reads.append(args["p_profile_id"])
        spend = self.spend_by_profile.get(args["p_profile_id"], 0.0)
        return [{"report_date": "2026-09-16", "ad_product": "SP", "cost": spend, "clicks": 1, "impressions": 1,
                 "purchases_7d": 0, "sales_7d": 0}] if spend else []


def test_a_name_is_compared_by_its_letters_and_digits_without_accents():
    assert name_key("Dermaglós & Co") == name_key("DERMAGLOS-CO") == "dermaglosco"


def test_a_profile_id_is_read_as_given():
    rest = _FakeRest({})

    assert choose_account(rest, "3", "otra cosa", days=7).profile_id == "3"
    assert rest.reads == []


def test_a_name_that_matches_one_account_reads_that_account():
    assert choose_account(_FakeRest({}), "", "acme pro", days=7).profile_id == "4"


def test_a_client_name_is_matched_exactly_before_it_is_read_as_part_of_another():
    """«Acme» names the Acme accounts, not Acme Pro too."""
    assert choose_account(_FakeRest({}), "", "Acme", days=7).profile_id == "3"


def test_a_name_that_matches_several_accounts_returns_them_with_what_each_spent():
    choice = choose_account(_FakeRest({"2": 50.0, "1": 10.0}), "", "dermaglos", days=7)
    payload = choice.as_payload()

    assert [(row["account"], row["spend"]) for row in payload["candidates"]] == [
        ("Dermaglós · MX", 50.0), ("Dermaglós · US", 10.0)]
    assert payload["rows"] == [] and "coincide con 2 cuentas" in payload["note"]


def test_a_name_no_account_has_or_no_account_at_all_is_refused():
    with pytest.raises(ValueError, match="Ninguna cuenta tiene «zzz»"):
        choose_account(_FakeRest({}), "", "zzz", days=7)
    with pytest.raises(ValueError, match="profile_id o account"):
        choose_account(_FakeRest({}), "", "  ", days=7)

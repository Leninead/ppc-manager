"""The analyses tools: what the chat reads about accounts that are not on screen, now that nothing is pasted."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from core.ai_analysis.store import StoredAnalysis
from core.amazon_ads.report_provider import ProfileOption
from services.mcp_server.tools import analyses


def _profile(profile_id: str, cliente: str, country: str = "US") -> ProfileOption:
    return ProfileOption(profile_id=profile_id, account_id=1, cliente=cliente, account_name=cliente,
                         country_code=country, currency_code="USD", account_type="seller", timezone="UTC",
                         status="active", data_from=date(2026, 7, 1), data_through=date(2026, 9, 16),
                         refreshed_on=None, last_success_at=None, last_error="")


def _stored(profile_id: str, module: str = "str", *, situation: str = "", params=None, negatives=(),
            harvest=(), records=(), synthesis=None) -> StoredAnalysis:
    return StoredAnalysis(
        id=1, module=module, subject_id=profile_id, window_start=date(2026, 8, 18), window_end=date(2026, 9, 16),
        lang="es", params=params or {}, params_digest="", input_digest="", agent_version="", status="done",
        trigger="scheduled", requested_by="", job_id=None, source_last_success_at=None,
        result={"synthesis": synthesis or {"situation": situation}}, model="", duration_ms=None, created_at=None,
        finished_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        negative_records=list(negatives), harvest_records=list(harvest), records=list(records))


@pytest.fixture
def data(monkeypatch):
    profiles = [_profile("1", "wamery"), _profile("2", "harrick")]
    stored = {"str": {}, "bid_optimizer": {}}

    class _Provider:
        def __init__(self, rest):
            pass

        def profiles(self):
            return profiles

    class _Store:
        def __init__(self, rest):
            pass

        def latest_by_subject(self, module, subject_ids):
            return [stored[module][s] for s in subject_ids if s in stored[module]]

    monkeypatch.setattr(analyses, "ReportProvider", _Provider)
    monkeypatch.setattr(analyses, "AiAnalysisStore", _Store)
    return stored


def test_the_index_carries_each_analysis_headline_so_accounts_compare_in_one_call(data):
    data["str"]["1"] = _stored("1", situation="ACoS 49.4% contra un target de 30%.", params={"target_acos": 30})
    data["str"]["2"] = _stored("2", situation="ACoS 78.8% contra un target de 30%.", params={"target_acos": 30})

    rows = {row["account"]: row for row in analyses.list_analyses(object())["rows"]}

    assert rows["wamery · US"]["situation"] == "ACoS 49.4% contra un target de 30%."
    assert rows["harrick · US"]["target_acos"] == 30


def test_the_headline_names_the_rows_it_cites_by_their_term_since_the_index_has_no_rows(data):
    data["str"]["1"] = _stored("1", situation="Frenar N02 y llevar H01 a exact.",
                               negatives=[{"Search Term": "brita"}, {"Search Term": "samsung filter"}],
                               harvest=[{"Search Term": "serrated knife sharpener"}])

    row = analyses.list_analyses(object())["rows"][0]

    assert row["situation"] == "Frenar «samsung filter» y llevar «serrated knife sharpener» a exact."


def test_a_long_headline_is_clipped_so_the_index_stays_an_index(data):
    data["str"]["1"] = _stored("1", situation="palabra " * 300)

    situation = analyses.list_analyses(object())["rows"][0]["situation"]

    assert len(situation) <= analyses.HEADLINE_MAX_CHARS + 1 and situation.endswith("…")


def test_an_analysis_that_only_has_an_executive_summary_still_has_a_headline(data):
    data["bid_optimizer"]["1"] = _stored("1", "bid_optimizer", synthesis={"executive_summary": "A01 a 111.1%."},
                                         records=[{"asin": "B0CYLMJJJC"}])

    row = analyses.list_analyses(object())["rows"][0]

    assert row["situation"] == "«B0CYLMJJJC» a 111.1%."


def test_every_row_of_an_analysis_carries_its_row_id(data):
    data["str"]["1"] = _stored("1", negatives=[{"Search Term": "brita"}, {"Search Term": "samsung"}],
                               harvest=[{"Search Term": "serrated"}])

    rows = analyses.get_analysis(object(), profile_id="1", module="str")["rows"]

    assert [row["row_id"] for row in rows["negativos"]["rows"]] == ["N01", "N02"]
    assert rows["harvest"]["rows"][0] == {"row_id": "H01", "Search Term": "serrated"}


def test_the_synthesis_names_the_term_behind_each_row_id_it_cites(data):
    data["bid_optimizer"]["1"] = _stored(
        "1", "bid_optimizer", records=[{"asin": "B0CYLMJJJC"}, {"asin": "B0F4KXZVNM"}],
        synthesis={"situation": "A02 empeoró.", "week_actions": ["Bajar A01 escalonado."],
                   "risks": [{"type": "Muestra", "detail": "A02 tiene 46 clicks.", "urgency": "media"}]})

    synthesis = analyses.get_analysis(object(), profile_id="1", module="bid_optimizer")["synthesis"]

    assert synthesis["situation"] == "A02 (B0F4KXZVNM) empeoró."
    assert synthesis["week_actions"] == ["Bajar A01 (B0CYLMJJJC) escalonado."]
    assert synthesis["risks"][0]["detail"] == "A02 (B0F4KXZVNM) tiene 46 clicks."
    assert synthesis["risks"][0]["urgency"] == "media"


def test_the_row_id_prefixes_are_the_ones_the_agents_gave_the_rows():
    """The MCP image does not carry the agents, so it keeps its own copy; this is what keeps them equal."""
    from ai.agents.bid_optimizer.context import ASIN_PREFIX
    from ai.agents.str.context import HARV_PREFIX, NEG_PREFIX

    assert analyses.ROW_IDS == {
        "str": (("negativos", NEG_PREFIX, "Search Term"), ("harvest", HARV_PREFIX, "Search Term")),
        "bid_optimizer": (("filas", ASIN_PREFIX, "asin"),),
    }
    assert set(analyses.ROW_IDS) == set(analyses.MODULES)


def test_the_index_carries_the_type_and_urgency_of_each_risk_so_risks_compare_across_accounts(data):
    """Without them the model answered that the analyses have no urgency, instead of looking."""
    data["str"]["1"] = _stored("1", synthesis={"situation": "s", "risks": [
        {"type": "CONQUISTA_BRITA", "detail": "Cinco de los diez candidatos...", "urgency": "ALTA"},
        {"type": "MARCA_NO_DECLARADA", "detail": "Parámetros no trae brand terms", "urgency": "MEDIA"}]})
    data["bid_optimizer"]["2"] = _stored("2", "bid_optimizer", synthesis={"situation": "s", "risks": [
        {"type": "Atribución de ASIN", "detail": "...", "urgency": "alta"}]})

    rows = {row["account"]: row for row in analyses.list_analyses(object())["rows"]}

    assert rows["wamery · US"]["risks"] == [{"type": "CONQUISTA_BRITA", "urgency": "alta"},
                                            {"type": "MARCA_NO_DECLARADA", "urgency": "media"}]
    assert rows["harrick · US"]["risks"] == [{"type": "Atribución de ASIN", "urgency": "alta"}]


def test_an_analysis_without_risks_says_so_with_an_empty_list(data):
    data["str"]["1"] = _stored("1", situation="s")

    assert analyses.list_analyses(object())["rows"][0]["risks"] == []


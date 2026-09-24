"""The analyses tools: what the chat reads about accounts that are not on screen, now that nothing is pasted."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from core.ai_analysis.store import StoredAnalysis
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.search_term import frame as canonical
from services.mcp_server.tools import analyses


def _profile(profile_id: str, cliente: str, country: str = "US", zone: str = "UTC") -> ProfileOption:
    return ProfileOption(profile_id=profile_id, account_id=1, cliente=cliente, account_name=cliente,
                         country_code=country, currency_code="USD", account_type="seller", timezone=zone,
                         status="active", data_from=date(2026, 7, 1), data_through=date(2026, 9, 16),
                         refreshed_on=None, last_success_at=None, last_error="")


def _stored(profile_id: str, module: str = "str", *, situation: str = "", params=None, negatives=(),
            harvest=(), records=(), synthesis=None,
            finished_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)) -> StoredAnalysis:
    return StoredAnalysis(
        id=1, module=module, subject_id=profile_id, window_start=date(2026, 8, 18), window_end=date(2026, 9, 16),
        lang="es", params=params or {}, params_digest="", input_digest="", agent_version="", status="done",
        trigger="scheduled", requested_by="", job_id=None, source_last_success_at=None,
        result={"synthesis": synthesis or {"situation": situation}}, model="", duration_ms=None, created_at=None,
        finished_at=finished_at,
        negative_records=list(negatives), harvest_records=list(harvest), records=list(records))


def _report_row(term: str, campaign: str, state: str) -> dict:
    return {canonical.SEARCH_TERM: term, canonical.CAMPAIGN_NAME: campaign, canonical.AD_GROUP_NAME: "AG",
            "_campaign_status": state}


@dataclass
class FakeProvider:
    """The accounts, and the search term report it answers with; `reads` keeps each window it was asked for."""
    profiles: list = field(default_factory=lambda: [_profile("1", "wamery"), _profile("2", "harrick")])
    search_terms: list = field(default_factory=list)
    reads: list = field(default_factory=list)
    error: Exception | None = None


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def data(monkeypatch, provider):
    stored = {module: {} for module in analyses.MODULES}

    class _Provider:
        def __init__(self, rest):
            pass

        def profiles(self):
            return provider.profiles

        def search_terms(self, option, start, end):
            provider.reads.append((option.profile_id, start, end))
            if provider.error:
                raise provider.error
            frame = pd.DataFrame(provider.search_terms, columns=list(_report_row("", "", "")))
            return canonical.SearchTermSource(frame=frame, source=canonical.SOURCE_API, currency_code="USD",
                                              label=option.label, signature="test", attribution_days=7,
                                              bulk_ready=True)

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
    assert rows["harvest"]["rows"][0] == {"row_id": "H01", "Search Term": "serrated", "campaign_state": ""}


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


def test_the_chat_is_told_a_count_in_the_analysis_prose_is_checked_against_its_rows(data):
    """An agent wrote «the four rows with history» over six: repeated as is, the chat's count was wrong too."""
    data["bid_optimizer"]["1"] = _stored("1", "bid_optimizer", situation="Las cuatro filas con historial bajaron.",
                                         records=[{"asin": "B0CYLMJJJC"}])

    index = analyses.list_analyses(object())
    analysis = analyses.get_analysis(object(), profile_id="1", module="bid_optimizer")

    assert index["situation_note"] == analyses.SITUATION_NOTE
    assert "se comprueba contando las filas de get_analysis antes de repetirla" in analyses.SITUATION_NOTE
    assert analysis["synthesis_note"] == analyses.SYNTHESIS_NOTE
    assert "sale de row_summary, que cuenta y suma todas las filas de cada grupo" in analyses.SYNTHESIS_NOTE


def test_the_summary_counts_and_sums_every_row_even_those_past_the_page(data):
    """The chat saw 21 of 60 Bulk Campañas rows and ranked campaigns over those: the summary covers all of them."""
    records = [{"campaign": f"Campaña {n}", "diagnostico": "PAUSAR" if n < 3 else "OK", "spend": 10.0, "orders": 1}
               for n in range(60)]
    data["bulk_campaigns"]["1"] = _stored("1", "bulk_campaigns", records=records)

    analysis = analyses.get_analysis(object(), profile_id="1", module="bulk_campaigns", limit=10)
    summary = analysis["row_summary"]["filas"]

    assert summary["rows"] == 60
    assert summary["counts"]["diagnostico"] == {"OK": 57, "PAUSAR": 3}
    assert "campaign" not in summary["counts"]
    assert summary["totals"] == {"spend": 600.0, "orders": 60}
    assert analysis["rows"]["filas"]["showing"] == 10
    assert "paging_note" in analysis


def test_the_rows_past_the_page_are_reached_with_the_group_and_offset(data):
    records = [{"campaign": f"Campaña {n}", "spend": float(n)} for n in range(30)]
    data["bulk_campaigns"]["1"] = _stored("1", "bulk_campaigns", records=records)

    later = analyses.get_analysis(object(), profile_id="1", module="bulk_campaigns", group="filas", offset=25)

    assert [row["row_id"] for row in later["rows"]["filas"]["rows"]] == ["C26", "C27", "C28", "C29", "C30"]
    with pytest.raises(ValueError, match="no tiene el grupo"):
        analyses.get_analysis(object(), profile_id="1", module="bulk_campaigns", group="harvest")


def test_each_metric_kept_with_its_previous_window_says_whether_it_went_up_or_down(data):
    """An agent wrote «the four rows with history lowered their CVR» over seven with history, one of them up."""
    records = [{"asin": "A", "cvr": 10.0, "cvr_previo": 12.0}, {"asin": "B", "cvr": 46.0, "cvr_previo": 30.0},
               {"asin": "C", "cvr": 0.0, "cvr_previo": 0.0}, {"asin": "D", "cvr": 5.0}]
    data["bid_optimizer"]["1"] = _stored("1", "bid_optimizer", records=records)

    analysis = analyses.get_analysis(object(), profile_id="1", module="bid_optimizer")

    assert [row["cvr_vs_previo"] for row in analysis["rows"]["filas"]["rows"]] == [
        "bajó", "subió", "igual", analyses.NO_PREVIOUS]
    assert analysis["row_summary"]["filas"]["counts"]["cvr_vs_previo"] == {
        "bajó": 1, "igual": 1, "sin tramo previo": 1, "subió": 1}


def test_the_row_id_prefixes_are_the_ones_the_agents_gave_the_rows():
    """The MCP image does not carry the agents, so it keeps its own copy; this is what keeps them equal."""
    from ai.agents.bid_optimizer.context import ASIN_PREFIX
    from ai.agents.bulk_campaigns.context import CAMPAIGN_PREFIX
    from ai.agents.ppc_insights.context import ASIN_PREFIX as INSIGHTS_PREFIX
    from ai.agents.str.context import HARV_PREFIX, NEG_PREFIX

    assert analyses.ROW_IDS == {
        "str": (("negativos", NEG_PREFIX, "Search Term"), ("harvest", HARV_PREFIX, "Search Term")),
        "bid_optimizer": (("filas", ASIN_PREFIX, "asin"),),
        "bulk_campaigns": (("filas", CAMPAIGN_PREFIX, "campaign"),),
        "ppc_insights": (("filas", INSIGHTS_PREFIX, "asin"),),
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


class TestSearchTermRowsSayTheStateOfTheirCampaignToday:
    """The saved rows only name the campaign («Viejo», «Pausada»): the chat promised spend a paused one never frees."""

    def test_each_row_carries_the_state_its_campaign_has_now(self, data, provider):
        provider.search_terms = [_report_row("sleep sack", "Luna - BROAD - Pausada", "PAUSED"),
                                 _report_row("luna pajamas", "Luna - EXACT - Viejo", "ENABLED")]
        data["str"]["1"] = _stored(
            "1", negatives=[{"Search Term": "sleep sack", "Campaign": "Luna - BROAD - Pausada", "Ad Group": "AG"}],
            harvest=[{"Search Term": "luna pajamas", "Campaign": "Luna - EXACT - Viejo", "Ad Group": "AG"}])

        payload = analyses.get_analysis(object(), profile_id="1", module="str")

        assert payload["rows"]["negativos"]["rows"][0]["campaign_state"] == "PAUSED"
        assert payload["rows"]["harvest"]["rows"][0]["campaign_state"] == "ENABLED"
        assert provider.reads == [("1", date(2026, 8, 18), date(2026, 9, 16))]

    def test_when_the_report_cannot_be_read_the_rows_go_without_state_and_the_answer_says_so(self, data, provider):
        provider.error = ReportReadError("timeout")
        data["str"]["1"] = _stored("1", negatives=[{"Search Term": "sleep sack", "Campaign": "C", "Ad Group": "AG"}])

        payload = analyses.get_analysis(object(), profile_id="1", module="str")

        assert "campaign_state" not in payload["rows"]["negativos"]["rows"][0]
        assert payload["campaign_state_note"] == analyses.CAMPAIGN_STATE_UNREAD_NOTE

    def test_modules_without_search_term_rows_read_no_report(self, data, provider):
        data["bid_optimizer"]["1"] = _stored("1", "bid_optimizer", records=[{"asin": "B0CYLMJJJC"}])

        analyses.get_analysis(object(), profile_id="1", module="bid_optimizer")

        assert provider.reads == []


def test_finished_at_is_on_each_accounts_clock_and_the_index_orders_by_the_instant(data, provider):
    """02:08 UTC on the 22nd is still the 21st in Los Angeles: the chat said the analysis ended a day ahead."""
    provider.profiles = [_profile("1", "wamery", zone="America/Los_Angeles"),
                         _profile("2", "harrick", country="JP", zone="Asia/Tokyo")]
    data["str"]["1"] = _stored("1", finished_at=datetime(2026, 9, 22, 2, 8, tzinfo=timezone.utc))
    data["str"]["2"] = _stored("2", finished_at=datetime(2026, 9, 21, 20, 0, tzinfo=timezone.utc))

    rows = analyses.list_analyses(object())["rows"]

    assert [(row["profile_id"], row["finished_at"]) for row in rows] == [("1", "2026-09-21T19:08:00-07:00"),
                                                                         ("2", "2026-09-22T05:00:00+09:00")]
    assert analyses.get_analysis(object(), profile_id="1", module="str")["finished_at"] == "2026-09-21T19:08:00-07:00"


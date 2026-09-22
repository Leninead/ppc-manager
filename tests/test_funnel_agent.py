"""The Análisis de Funnel agent: what travels to the model, the row ids, and how its answer reads in the chat."""
import pandas as pd

from ai.agent_call import build_agent_call
from ai.agents.funnel import chat_document
from ai.agents.funnel.context import MAX_GAPS, build_context
from core.funnel.analysis import ANALYSIS_MODULE, build_analysis_input, funnel_row_labels
from core.funnel.coverage import cover, harvest_candidates, suggested_campaigns
from core.search_term.frame import add_ratios

EXACT_BRAND = "Luna - B0CYLMJJJC - SP - KW - EXACT - Brand"


def _term(term, campaign, campaign_id, *, clicks, orders, sales, spend):
    return {"Customer Search Term": term, "Campaign Name": campaign, "Ad Group Name": "AG", "Impressions": 100,
            "Clicks": clicks, "Spend": spend, "7 Day Total Sales": sales, "7 Day Total Orders (#)": orders,
            "_campaign_id": campaign_id}


TERMS = [
    _term("luna pajamas", EXACT_BRAND, "1", clicks=30, orders=6, sales=150.0, spend=10.0),
    _term("sleep sack", "Old Broad", "3", clicks=20, orders=0, sales=0.0, spend=15.0),
    _term("baby bag", "Luna - B0CYLM4L23 - SP - KW - BROAD - Old", "9", clicks=5, orders=1, sales=20.0, spend=4.0),
]
CAMPAIGNS = pd.DataFrame([
    {"Campaign name": EXACT_BRAND, "Campaign ID": "1", "State": "ENABLED", "Type": "Sponsored Products",
     "Campaign budget amount": 20.0, "Impressions": 900, "Clicks": 30, "Total cost": 10.0, "Purchases": 6,
     "Sales": 150.0},
    {"Campaign name": "Old Broad", "Campaign ID": "3", "State": "PAUSED", "Type": "Sponsored Products",
     "Campaign budget amount": 5.0, "Impressions": 0, "Clicks": 0, "Total cost": 0.0, "Purchases": 0, "Sales": 0.0},
    {"Campaign name": "Small Ghost", "Campaign ID": "4", "State": "ENABLED", "Type": "Sponsored Products",
     "Campaign budget amount": 5.0, "Impressions": 0, "Clicks": 0, "Total cost": 0.0, "Purchases": 0, "Sales": 0.0},
    {"Campaign name": "Big Ghost", "Campaign ID": "5", "State": "ENABLED", "Type": "Sponsored Products",
     "Campaign budget amount": 50.0, "Impressions": 1200, "Clicks": 0, "Total cost": 0.0, "Purchases": 0,
     "Sales": 0.0},
])


def _input(rows=TERMS, min_orders=3, **overrides):
    frame = add_ratios(pd.DataFrame(rows), 7)
    coverage = cover(frame, CAMPAIGNS, match_by_id=True)
    options = {"account_label": "Luna Kids · US", "period_label": "8 – 14 sep 2026", "currency_code": "USD",
               "attribution_days": 7, "min_orders": min_orders, "match_type": "Phrase", "lang": "es"}
    options.update(overrides)
    return build_analysis_input(coverage, harvest_candidates(frame, coverage, min_orders),
                                suggested_campaigns(coverage.gap_terms, coverage.columns, "Phrase"), **options)


def test_row_ids_run_once_across_the_three_groups():
    built = _input()
    _, docs, _ = build_context(built.data)

    assert [record["grupo"] for record in built.records] == ["harvest", "brecha", "brecha", "sin_trafico",
                                                             "sin_trafico"]
    assert funnel_row_labels(built.records) == {"F01": "luna pajamas", "F02": "sleep sack", "F03": "baby bag",
                                                "F04": "Big Ghost", "F05": "Small Ghost"}
    assert [doc["title"] for doc in docs] == [
        "Parámetros", "Candidatos a harvest (1 filas)", "Términos de campañas pausadas o inexistentes (2 filas)",
        "Campañas activas sin search terms (2 filas)"]
    assert docs[2]["content"].splitlines()[1].startswith("F02,sleep sack,Old Broad,PAUSED")
    assert "grupo" not in docs[1]["content"].splitlines()[0]


def test_idle_campaigns_come_largest_budget_first_with_their_campaign_metrics():
    idle = [record for record in _input().records if record["grupo"] == "sin_trafico"]

    assert idle[0] == {"grupo": "sin_trafico", "campana": "Big Ghost", "presupuesto": 50, "impressions": 1200,
                       "clicks": 0, "spend": 0, "orders": 0, "sales": 0}


def test_the_parameters_state_the_cross_the_minimum_and_the_whole_account_figures():
    _, docs, _ = build_context(_input().data)
    params = docs[0]["content"]

    assert "Cruce de search terms con campañas: por Campaign ID" in params
    assert "Mínimo de órdenes para harvest: 3" in params
    assert "- Campañas activas sin search terms: 2" in params
    assert "Viajaron todos los candidatos a harvest: 1." in params


def test_the_parameters_split_what_sold_in_active_campaigns_from_the_rest():
    _, docs, _ = build_context(_input().data)
    params = docs[0]["content"]

    assert "- Órdenes de search terms en campañas activas: 6" in params
    assert "- Ventas de search terms en campañas activas: 150" in params
    assert "- Órdenes de search terms en campañas pausadas o inexistentes: 1" in params
    assert "- Ventas de search terms en campañas pausadas o inexistentes: 20" in params


def test_each_harvest_row_says_whether_it_still_runs_in_an_active_campaign():
    harvest = [record for record in _input(min_orders=1).records if record["grupo"] == "harvest"]

    assert {record["termino"]: record["en_campana_activa"] for record in harvest} == {
        "luna pajamas": True, "baby bag": False}


def test_a_group_bigger_than_its_cap_says_how_many_rows_were_left_out():
    rows = [_term(f"term {index}", f"Gone {index}", f"g{index}", clicks=3, orders=0, sales=0.0, spend=float(index))
            for index in range(MAX_GAPS + 5)]

    built = _input(rows)
    _, docs, _ = build_context(built.data)

    assert f"De {MAX_GAPS + 5} términos de campañas pausadas o inexistentes viajaron {MAX_GAPS}" in docs[0]["content"]
    assert len([record for record in built.records if record["grupo"] == "brecha"]) == MAX_GAPS


def test_nothing_to_judge_builds_no_payload():
    campaigns_with_traffic = CAMPAIGNS[CAMPAIGNS["Campaign ID"].isin(["1"])]
    frame = add_ratios(pd.DataFrame(TERMS[:1]), 7)
    coverage = cover(frame, campaigns_with_traffic, match_by_id=True)

    built = build_analysis_input(coverage, harvest_candidates(frame, coverage, 10),
                                 suggested_campaigns(coverage.gap_terms, coverage.columns, "Phrase"),
                                 account_label="x", period_label="", currency_code="", attribution_days=7,
                                 min_orders=10, match_type="Phrase", lang="es")

    assert built.data is None and built.records == []


def test_the_same_data_digests_the_same_and_another_minimum_does_not():
    first, same = build_agent_call(ANALYSIS_MODULE, _input().data), build_agent_call(ANALYSIS_MODULE, _input().data)
    other = build_agent_call(ANALYSIS_MODULE, _input(min_orders=1).data)

    assert first.input_digest == same.input_digest
    assert first.input_digest != other.input_digest
    assert first.agent_version


def test_the_chat_reading_names_the_term_or_campaign_behind_every_row_id():
    built = _input()
    result = {"synthesis": {"situation": "Hay una campaña grande sin tráfico.", "week_actions": ["Revisar F04"],
                            "mid_term": [], "risks": [], "executive_summary": "1 término para cosechar."},
              "filas": [{"row_id": "F04", "razon": "1.200 impresiones sin clicks.", "veredicto": "INVESTIGAR",
                         "confianza": "media", "advertencia": None},
                        {"row_id": "F99", "razon": "no existe", "veredicto": "ACTUAR", "confianza": "alta",
                         "advertencia": None}]}

    text = chat_document.reading_text(result, built.records)

    assert "F04 · sin_trafico · Big Ghost → INVESTIGAR · media: 1.200 impresiones sin clicks." in text
    assert "F99" not in text

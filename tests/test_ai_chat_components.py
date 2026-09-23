"""The chat panel with components: the tools behind an answer and the answer as the thread draws it."""
import pytest
from streamlit.testing.v1 import AppTest

from ai import runtime
from core.chat import panel
from core.chat.components.base import TONE_COLOR

ES = panel._L["es"]
EN = panel._L["en"]


@pytest.mark.parametrize("name, label", [
    ("mcp__amazon_ads__campaign_management-query_campaign", "Campañas · Amazon Ads"),
    ("mcp__amazon_ads__campaign_management-query_ad_group", "Ad groups · Amazon Ads"),
    ("mcp__amazon_ads__campaign_management-query_target", "Targets · Amazon Ads"),
    ("mcp__amazon_ads__account_management-query_advertiser_account", "Cuentas · Amazon Ads"),
    ("mcp__amazon_ads__reporting-retrieve_campaign_report", "Reportes · Amazon Ads"),
    ("mcp__amazon_ads__something_new-query_thing", "Amazon Ads"),
    ("mcp__datadive__get_niche_keywords", "Keywords · DataDive"),
    ("mcp__datadive__get_niche_competitors", "Competidores · DataDive"),
    ("mcp__datadive__list_niches", "Niches · DataDive"),
    ("mcp__datadive__list_rank_radars", "Rank Radar · DataDive"),
    ("mcp__ppc_manager__list_analyses", "Análisis · Agency OS"),
    ("mcp__ppc_manager__get_analysis", "Análisis · Agency OS"),
    ("mcp__ppc_manager__top_search_terms", "Search terms · Agency OS"),
    ("mcp__ppc_manager__list_accounts", "Cuentas · Agency OS"),
    ("mcp__ppc_manager__daily_metrics", "Serie diaria · Agency OS"),
    ("mcp__ppc_manager__breakdown", "Desglose · Agency OS"),
    ("mcp__ppc_manager__funnel_coverage", "Funnel · Agency OS"),
    ("mcp__ppc_manager__search_term_candidates", "Candidatos · Agency OS"),
    ("mcp__ppc_manager__bid_suggestions", "Bids · Agency OS"),
    ("mcp__ppc_manager__asin_health", "Salud por ASIN · Agency OS"),
    ("mcp__ppc_manager__campaign_health", "Diagnóstico de campañas · Agency OS"),
    ("mcp__ppc_manager__idle_targets", "Targets sin impresiones · Agency OS"),
    ("mcp__ppc_manager__campaign_structure", "Estructura de campañas · Agency OS"),
    ("mcp__ppc_manager__something_new", "Agency OS"),
])
def test_a_tool_is_named_by_what_it_reads(name, label):
    assert panel._tool_label(name, ES) == label


def test_every_app_tool_names_what_it_reads():
    from services.mcp_server.server import build_tools

    names = [tool["name"] for tool in build_tools(rest=None)]
    unnamed = [name for name in names if panel._tool_label(f"mcp__ppc_manager__{name}", ES) == ES["src_ppc_manager"]]

    assert names and unnamed == []


@pytest.mark.parametrize("name", ["Skill", "Read", "StructuredOutput", "mcp__datadive__get_quota",
                                  "mcp__other__query_campaign"])
def test_machinery_is_not_a_source(name):
    assert panel._tool_label(name, ES) is None


def test_labels_follow_the_panel_language():
    assert panel._tool_label("mcp__amazon_ads__campaign_management-query_campaign", EN) == \
        "Campaigns · Amazon Ads"


def test_the_same_source_read_twice_is_one_chip():
    names = ["Skill", "mcp__amazon_ads__campaign_management-query_campaign",
             "mcp__amazon_ads__account_management-query_advertiser_account",
             "mcp__amazon_ads__campaign_management-query_campaign"]
    assert panel._tool_labels(names, ES) == ["Campañas · Amazon Ads", "Cuentas · Amazon Ads"]


def test_chips_and_bubble_travel_in_one_element_so_the_reversed_thread_keeps_them_in_order():
    html = panel._assistant_turn({"role": "assistant", "text": "Hay 3", "tools": ["Campañas · Amazon Ads"]})
    assert html.startswith("<div>") and html.endswith("</div></div>")
    assert html.index("Campañas · Amazon Ads") < html.index("Hay 3")


def test_an_answer_without_components_is_drawn_from_its_prose():
    html = panel._assistant_bubble("Solo **texto**\n- uno", None)
    assert "<b>texto</b>" in html and "•" in html


def test_an_answer_in_components_reaches_the_thread_with_its_chips_and_its_annotation(monkeypatch):
    structured = {"blocks": [
        {"kind": "text", "text": "Frenar N01"},
        {"kind": "kpis", "items": [{"label": "ACoS", "value": "48.8%", "detail": "target 30%", "tone": "bad"},
                                   {"label": "Órdenes", "value": "198", "detail": "", "tone": "neutral"}]},
        {"kind": "bars", "metric": "Gasto sin ventas", "items": [
            {"label": "N01", "value": 32.24, "display": "$32.24", "tone": "bad"},
            {"label": "N02", "value": 10, "display": "$10.00", "tone": "neutral"}]},
        {"kind": "action", "text": "Pausar N01"},
    ]}
    events = [{"type": "tool", "name": "mcp__amazon_ads__campaign_management-query_campaign"},
              {"type": "result", "text": "prosa previa", "structured_output": structured, "session_id": "s1",
               "tool_calls": ["Skill", "mcp__amazon_ads__campaign_management-query_campaign"]}]
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: iter(events))
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string("""
from core.chat.panel import ChatTurn, floating_chat
floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k", turn=lambda: ChatTurn(
    annotate=lambda text: text.replace("N01", "N01 (toy box)")))
""", default_timeout=30)
    app.run()
    app.text_area(key="aichat_t_q_0").input("¿qué frenamos?")
    app.button[0].click()
    app.run()
    app.run()

    assert not app.exception
    answer = app.session_state["aichat_t_hist"][1]
    assert answer["tools"] == ["Campañas · Amazon Ads"]
    assert [block["kind"] for block in answer["blocks"]] == ["text", "kpis", "bars", "action"]
    assert answer["text"].startswith("Frenar N01\n\nACoS: 48.8% (target 30%)")
    assert answer["shown"].count("N01 (toy box)") == 3 and "prosa previa" not in answer["shown"]
    html = " ".join(str(block.value) for block in app.markdown)
    assert "Campañas · Amazon Ads" in html and "Gasto sin ventas" in html
    assert "&#36;32.24" in html and TONE_COLOR["bad"] in html and "N01 (toy box)" in html


PORTFOLIOS = "mcp__amazon_ads__campaign_management-query_portfolio"
SERIES = "mcp__ppc_manager__daily_metrics"


@pytest.mark.parametrize("asked, failed, expected", [
    ([PORTFOLIOS], [PORTFOLIOS], ["Portfolios · Amazon Ads"]),
    ([PORTFOLIOS, PORTFOLIOS], [PORTFOLIOS, PORTFOLIOS], ["Portfolios · Amazon Ads"]),
    # One call that answered is enough: that source did reach the answer.
    ([PORTFOLIOS, PORTFOLIOS], [PORTFOLIOS], []),
    # A call still running has not failed.
    ([PORTFOLIOS], [], []),
    ([PORTFOLIOS, SERIES], [PORTFOLIOS], ["Portfolios · Amazon Ads"]),
    (["StructuredOutput"], ["StructuredOutput"], []),
])
def test_a_source_counts_as_failed_only_when_every_call_to_it_failed(asked, failed, expected):
    assert panel._failed_labels(asked, failed, ES) == expected


def test_a_failed_source_reads_as_failed_on_the_chip_itself_not_only_in_its_color():
    """Nothing hover-only: on a phone the word is what tells the AM that source brought nothing."""
    html = panel._tools_row(["Serie diaria · Agency OS", "Portfolios · Amazon Ads"],
                            failed=["Portfolios · Amazon Ads"], failed_note=ES["tool_failed"])
    assert "Serie diaria · Agency OS</span>" in html
    assert "Portfolios · Amazon Ads · falló</span>" in html
    assert html.count("dashed") == 1


def test_a_turn_stored_before_outcomes_existed_still_draws_its_chips():
    html = panel._assistant_turn({"role": "assistant", "text": "Hay 3", "tools": ["Campañas · Amazon Ads"]},
                                 ES["tool_failed"])
    assert "Campañas · Amazon Ads</span>" in html and "falló" not in html


def test_a_source_that_failed_is_marked_in_the_thread_once_the_answer_lands(monkeypatch):
    structured = {"blocks": [{"kind": "text", "text": "No pude leer los portfolios."}]}
    events = [{"type": "tool", "name": PORTFOLIOS},
              {"type": "tool_result", "name": PORTFOLIOS, "ok": False},
              {"type": "tool", "name": SERIES},
              {"type": "tool_result", "name": SERIES, "ok": True},
              {"type": "result", "text": "", "structured_output": structured, "session_id": "s1",
               "tool_calls": [PORTFOLIOS, SERIES], "failed_tools": [PORTFOLIOS]}]
    monkeypatch.setattr(runtime.client, "ask_stream", lambda **call: iter(events))
    monkeypatch.setattr(runtime, "usable_tools", lambda slug, scope: [])
    monkeypatch.setattr(runtime.chat_skills, "enabled_payload", lambda: [])
    app = AppTest.from_string("""
from core.chat.panel import ChatTurn, floating_chat
floating_chat(chat_id="t", agent="orchestrator", session_key=lambda: "k", turn=lambda: ChatTurn())
""", default_timeout=30)
    app.run()
    app.text_area(key="aichat_t_q_0").input("¿portfolios?")
    app.button[0].click()
    app.run()
    app.run()

    assert not app.exception
    answer = app.session_state["aichat_t_hist"][1]
    assert answer["tools"] == ["Portfolios · Amazon Ads", "Serie diaria · Agency OS"]
    assert answer["tools_failed"] == ["Portfolios · Amazon Ads"]
    html = " ".join(str(block.value) for block in app.markdown)
    assert "Portfolios · Amazon Ads · falló" in html and "Serie diaria · Agency OS</span>" in html

"""Stored analyses are found by the digest of what their agent reads.

These payloads are pinned to the exact digest they had when the rules moved out of the AI payload
modules (so the MCP could read them): if moving code changed a byte, the worker would pay again for
the analysis of every account. A deliberate payload change updates these values in the same commit.
"""
import pandas as pd

from ai.agent_call import build_agent_call
from core.bid_optimizer.analysis import build_analysis_input as build_bid_input
from core.bid_optimizer.bids import BidAnalysisParams
from core.ppc_insights.analysis import build_analysis_input as build_insights_input
from core.ppc_insights.asin_health import InsightsAnalysisParams
from core.search_term.analysis import build_analysis_input as build_str_input
from core.search_term.candidates import StrAnalysisParams, add_metric_columns, detect_columns
from core.search_term.frame import add_ratios

_ROWS = [
    {"Customer Search Term": "cheap toy box", "Campaign Name": "LK - B0CYLMJJJC - SP - KW - BROAD - Discovery",
     "Ad Group Name": "AG1", "Match Type": "BROAD", "Impressions": 900, "Clicks": 40, "Spend": 25.0,
     "7 Day Total Sales": 0.0, "7 Day Total Orders (#)": 0, "_ad_group_id": "11"},
    {"Customer Search Term": "luna pajamas", "Campaign Name": "LK - B0CYLMJJJC - SP - KW - EXACT - Brand",
     "Ad Group Name": "AG2", "Match Type": "EXACT", "Impressions": 800, "Clicks": 30, "Spend": 10.0,
     "7 Day Total Sales": 150.0, "7 Day Total Orders (#)": 6, "_ad_group_id": "12"},
    {"Customer Search Term": "sleep sack", "Campaign Name": "LK - B0CYLM4L23 - SP - KW - PHRASE - Core",
     "Ad Group Name": "AG3", "Match Type": "PHRASE", "Impressions": 100, "Clicks": 2, "Spend": 1.0,
     "7 Day Total Sales": 0.0, "7 Day Total Orders (#)": 0, "_ad_group_id": "13"},
    {"Customer Search Term": "baby sleeping bag", "Campaign Name": "LK - B0CYLM4L23 - SP - KW - PHRASE - Core",
     "Ad Group Name": "AG3", "Match Type": "PHRASE", "Impressions": 1500, "Clicks": 60, "Spend": 42.5,
     "7 Day Total Sales": 310.0, "7 Day Total Orders (#)": 11, "_ad_group_id": "13"},
]


def _frame():
    return add_ratios(pd.DataFrame(_ROWS), 7)


def test_the_search_term_payload_keeps_its_digest():
    frame = _frame()
    cols = detect_columns(frame)
    add_metric_columns(frame, cols)
    params = StrAnalysisParams.defaults("USD")
    built = build_str_input(frame, cols, params, currency_code="USD", lang="es")

    assert params.digest == "65f9cf5698e2da6f758864cfb8775ff5f608ebb47fc000de144d042f94772f9b"
    assert build_agent_call("str", built.data).input_digest == (
        "ec2e9a8849b588118f96d8cd2b39d785f1c01d9eff780ba1771491add9a49a60")


def test_the_bid_optimizer_payload_keeps_its_digest():
    built = build_bid_input(_frame(), target_acos=25, account_label="Luna Kids · US", period_label="8 – 14 sep 2026",
                            currency_code="USD")

    assert BidAnalysisParams(25).digest == "d5e28000de4c4e758c2e3a3fe1aa354282495b955d8473f0c1fe810ad4db7a1e"
    assert build_agent_call("bid_optimizer", built.data).input_digest == (
        "17fa9dd9b3496606eeb724812b033de6c267f6474b1b9544f5cd39f93391d3a0")


def test_the_ppc_insights_payload_keeps_its_digest():
    params = InsightsAnalysisParams(25, 15.0)
    built = build_insights_input(_frame(), params=params, account_label="Luna Kids · US",
                                 period_label="8 – 14 sep 2026", currency_code="USD",
                                 ad_group_asins={"11": frozenset({"B0CYLMJJJC"}),
                                                 "13": frozenset({"B0CYLM4L23", "B0CYLMAAAA"})})

    assert params.digest == "064e985e022207cd8ecd433e484dfc24891419c4e2262a851150a80e6b22af01"
    assert build_agent_call("ppc_insights", built.data).input_digest == (
        "6f6d72bf6cb5b58fb2927654904b0dfda6ae5452a58849ecfbf9942f00ac227b")

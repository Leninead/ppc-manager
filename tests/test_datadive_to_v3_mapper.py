"""Tests del mapper datadive_to_v3_block (E3 / E4-integración).

DataFrames hand-built (sin .xlsx). El mapper es función pura que produce un
ImportReport reusable por merge_blocks.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from modules.sales.mappers.datadive_to_v3 import datadive_to_v3_block, V3_MODULE_ID
from modules.sales.b7_importer import merge_blocks

CLIENT = "B0CLIENT01"
COMP = "B0COMPET01"

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "data" / "sales" / "_catalog.json"
DEMO_PROPOSAL_PATH = (
    REPO_ROOT / "data" / "sales" / "proposals"
    / "01fbf5c2-1fd9-44dd-9806-742e5deb8f71__v12.json"
)


# ── 1-8: mapper puro ─────────────────────────────────────────────────────────

def test_mapper_invalid_asin_returns_error_report():
    df = pd.DataFrame([{"Search Term": "kw", "SV": 100, "Launch Score": 5.0}])
    report = datadive_to_v3_block(df, [], "INVALID")
    assert not report.ok
    assert any(e.code == "invalid_asin" for e in report.errors)


def test_mapper_client_asin_not_in_competitors_returns_warning():
    df = pd.DataFrame([{"Search Term": "kw", "SV": 100, "Launch Score": 5.0, COMP: 5}])
    report = datadive_to_v3_block(df, [COMP], CLIENT)
    assert report.ok
    assert any(w.code == "client_asin_not_in_mkl" for w in report.warnings)


def test_mapper_filters_only_weak_ranks():
    df = pd.DataFrame([
        {"Search Term": "strong", "SV": 500, "Launch Score": 8.0, CLIENT: 5},
        {"Search Term": "weak", "SV": 400, "Launch Score": 6.0, CLIENT: 45},
        {"Search Term": "missing", "SV": 300, "Launch Score": 4.0, CLIENT: None},
    ])
    report = datadive_to_v3_block(df, [CLIENT], CLIENT)
    kws = [m["keyword"] for m in report.blocks[0].data["missing_keywords"]]
    assert "weak" in kws
    assert "missing" in kws
    assert "strong" not in kws


def test_mapper_excludes_strong_ranks():
    df = pd.DataFrame([
        {"Search Term": "r1", "SV": 100, "Launch Score": 5.0, CLIENT: 1},
        {"Search Term": "r30", "SV": 100, "Launch Score": 5.0, CLIENT: 30},  # 30 no es > 30
    ])
    report = datadive_to_v3_block(df, [CLIENT], CLIENT)
    assert report.blocks[0].data["missing_keywords"] == []


def test_mapper_opportunity_score_clamped_to_one():
    df = pd.DataFrame([{"Search Term": "kw", "SV": 100, "Launch Score": 15.0, CLIENT: None}])
    report = datadive_to_v3_block(df, [CLIENT], CLIENT)
    item = report.blocks[0].data["missing_keywords"][0]
    assert item["opportunity_score"] == 1.0


def test_mapper_empty_mkl_returns_empty_block():
    report = datadive_to_v3_block(pd.DataFrame(), [], CLIENT)
    assert report.ok
    assert len(report.blocks) == 1
    assert report.blocks[0].module_id == V3_MODULE_ID
    assert report.blocks[0].data["missing_keywords"] == []
    assert report.blocks[0].data["launch_score_table"] == []
    assert report.blocks[0].data["page1_domination_chart_data"] == []


def test_mapper_sorts_by_sv_desc():
    df = pd.DataFrame([
        {"Search Term": "low", "SV": 100, "Launch Score": 5.0, CLIENT: None},
        {"Search Term": "high", "SV": 900, "Launch Score": 5.0, CLIENT: None},
        {"Search Term": "mid", "SV": 500, "Launch Score": 5.0, CLIENT: None},
    ])
    report = datadive_to_v3_block(df, [CLIENT], CLIENT)
    kws = [m["keyword"] for m in report.blocks[0].data["missing_keywords"]]
    assert kws == ["high", "mid", "low"]


def test_mapper_truncates_to_top_50():
    # Decisión 8: capeamos a top 50 missing (por SV desc) para no inflar la propuesta.
    rows = [{"Search Term": f"kw{i}", "SV": i, "Launch Score": 5.0, CLIENT: None} for i in range(60)]
    report = datadive_to_v3_block(pd.DataFrame(rows), [CLIENT], CLIENT)
    missing = report.blocks[0].data["missing_keywords"]
    assert len(missing) == 50
    assert missing[0]["keyword"] == "kw59"  # mayor SV primero


# ── 9: integración con merge_blocks (E4-ready) ───────────────────────────────

def test_v3_report_merges_via_merge_blocks():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    with open(DEMO_PROPOSAL_PATH, "r", encoding="utf-8") as f:
        proposal = json.load(f)

    df = pd.DataFrame([
        {"Search Term": "missing kw", "SV": 800, "Launch Score": 7.0, CLIENT: None},
    ])
    report = datadive_to_v3_block(df, [CLIENT], CLIENT)
    result = merge_blocks(report, proposal, catalog)
    assert result.ok
    assert "V3_seo_opportunity" in result.applied_blocks
    # el data del bloque V3 quedó overwriteado con las missing keywords del mapper
    v3 = next(b for b in result.proposal_updated["blocks"]
              if b["module_id"] == "V3_seo_opportunity")
    assert any(m["keyword"] == "missing kw" for m in v3["data"]["missing_keywords"])

"""ppc_audit (MCP): PPC Audit Pro of a synced account, with the page's reads and rules. No network."""
import json
from datetime import date

import pytest

from core.ppc_audit.synced_reads import NOT_LISTED_REASON
from services.mcp_server.tools.ppc_audit import SECTION_WHAT, TARGET_TYPES_NEED_BRAND_TERMS, ppc_audit
from tests.test_ppc_audit_frames import PROFILE_ID, SYNCED_JOBS, AuditRest, job_row

WINDOW = {"date_from": "2026-09-09", "date_to": "2026-09-22"}


def _audit(rest=None, **arguments) -> dict:
    return ppc_audit(rest or AuditRest(), profile_id=PROFILE_ID, **{**WINDOW, **arguments})


def test_the_graduation_section_lists_the_quiet_keywords_with_the_accounts_summary():
    payload = _audit(section="graduation")

    assert payload["rows"] == [{"keyword": "kids sleep sack", "match_type": "Exact",
                                "campaign": "Luna - SP - KW - EXACT", "ad_group": "Core", "bid": 0.6,
                                "campaign_impressions": 1500, "spend": 0, "sales": 0, "orders": 0,
                                "recommendation": "GRADUAR A SKAG"}]
    assert payload["window"] == {"from": "2026-09-09", "to": "2026-09-22", "days": 14}
    assert payload["currency"] == "USD" and payload["attribution_days"] == 7
    summary = payload["summary"]
    assert set(summary["products"]) == {"SP", "SB", "SD"}
    assert summary["products"]["SP"]["spend"] == 45 and summary["totals"]["spend"] == 65
    assert summary["graduation"] == {"GRADUAR A SKAG": 1}
    assert summary["search_term_waste"]["sb"]["spend_without_sales"] == 3
    assert "missing" not in payload


@pytest.mark.parametrize("section", list(SECTION_WHAT))
def test_every_section_answers_a_page_that_serializes(section):
    payload = _audit(section=section, brand_terms=("luna",))

    json.dumps(payload)
    assert payload["total"] == len(payload["rows"]) or "note" in payload


def test_the_placements_and_the_segments_use_the_names_the_page_shows():
    placements = _audit(section="placements")["rows"]
    segments = _audit(section="segments")["rows"]

    assert placements == [{"placement": "Top of Search", "enabled_campaigns": 1, "average_pct": 50,
                           "min_pct": 50, "max_pct": 50, "campaigns_adjusting": 1}]
    auto = next(row for row in segments if row["segment"] == "AUTO Close Match")
    assert (auto["product"], auto["spend"], auto["targets"]) == ("SP", 15, 1)
    assert [row["segment"] for row in segments if row["product"] == "SB"] == ["KW Exact", "KW Phrase", "KW Broad",
                                                                               "TOTAL SB"]


def test_target_types_need_brand_terms():
    without = _audit(section="target_types")
    with_terms = _audit(section="target_types", brand_terms=("Luna",))

    assert without["rows"] == [] and TARGET_TYPES_NEED_BRAND_TERMS in without["missing"]
    assert with_terms["parameters"] == {"brand_terms": ["luna"]}
    assert {row["type"] for row in with_terms["rows"]} == {"own_brand", "generic"}


def test_an_account_never_listed_says_why_instead_of_answering_zeros():
    payload = _audit(AuditRest(structure=[], jobs=[job_row("sp_search_terms")]), section="skag")

    assert payload["rows"] == [] and payload["missing"] == [NOT_LISTED_REASON]
    assert "summary" not in payload


def test_metrics_that_stop_before_the_window_ends_are_noted():
    jobs = [job_row("sp_targeting", window_end=date(2026, 9, 20)) if job["job_kind"] == "sp_targeting" else job
            for job in SYNCED_JOBS]

    payload = _audit(AuditRest(jobs=jobs), section="duplicates")

    assert any("keywords y targets llegan hasta el 2026-09-20" in note for note in payload["missing"])


def test_an_unknown_section_is_refused_before_reading():
    rest = AuditRest()

    with pytest.raises(ValueError, match="section tiene que ser uno de"):
        _audit(rest, section="negatives")
    assert rest.reads == []

"""report_kinds: what each report the worker ingests is wired to. Pure, no I/O."""
from __future__ import annotations

import pytest

from core.amazon_ads import product_rows, report_kinds
from core.amazon_ads.report_fetcher import ReportFetcher, SbV2ReportFetcher
from core.amazon_ads.sync_planner import PRODUCT_CHUNK_DAYS, SB_LEGACY_SEARCH_TERMS_KIND, SB_SEARCH_TERMS_KIND


def test_v3_sb_search_terms_write_their_own_table_with_the_slice_of_the_other_product_reports():
    kind = report_kinds.by_job_kind(SB_SEARCH_TERMS_KIND)

    assert kind is report_kinds.SB_SEARCH_TERMS and report_kinds.by_name("sb_search_terms") is kind
    # Their table is SB's alone, so the day takes no ad product.
    assert (kind.spec, kind.replace_day_rpc, kind.rpc_args, kind.fetcher) == (
        product_rows.SB_SEARCH_TERM_SPEC, "replace_sb_search_term_day", {}, ReportFetcher)
    assert (kind.chunk_days, kind.max_inflight_reports, kind.max_creates_per_tick, kind.max_saves_per_tick) == (
        PRODUCT_CHUNK_DAYS, 3, 3, 3)
    assert kind.day_rows == product_rows.SB_SEARCH_TERM_ROWS.day_rows


def test_v2_sb_search_terms_go_a_day_at_a_time_and_write_their_days_as_the_v2_source():
    kind = report_kinds.by_job_kind(SB_LEGACY_SEARCH_TERMS_KIND)

    assert kind is report_kinds.SB_LEGACY_SEARCH_TERMS and report_kinds.by_name("sb_legacy_search_terms") is kind
    assert (kind.spec, kind.replace_day_rpc, kind.rpc_args, kind.fetcher, kind.chunk_days) == (
        product_rows.SB_LEGACY_SEARCH_TERM_SPEC, "replace_sb_search_term_day", {"p_source": "v2"}, SbV2ReportFetcher,
        1)
    assert (kind.max_inflight_reports, kind.max_creates_per_tick, kind.max_saves_per_tick) == (6, 6, 6)
    assert kind.day_rows == product_rows.SB_LEGACY_SEARCH_TERM_ROWS.day_rows


@pytest.mark.parametrize("kind, rpc_args", [
    (report_kinds.SP_TARGETING, {"p_ad_product": "SP"}),
    (report_kinds.SD_CAMPAIGNS, {"p_ad_product": "SD"}),
    (report_kinds.SD_TARGETING, {"p_ad_product": "SD"}),
    (report_kinds.SB_CAMPAIGNS, {"p_ad_product": "SB"}),
    (report_kinds.SB_TARGETING, {"p_ad_product": "SB"}),
    (report_kinds.SB_LEGACY_CAMPAIGNS, {"p_ad_product": "SB", "p_source": "v2"}),
], ids=lambda value: value.name if isinstance(value, report_kinds.ReportKind) else "")
def test_the_other_product_reports_keep_their_replace_arguments(kind, rpc_args):
    assert kind.rpc_args == rpc_args


def test_the_v2_campaign_report_keeps_its_one_day_chunks_and_its_slots():
    kind = report_kinds.SB_LEGACY_CAMPAIGNS

    assert (kind.fetcher, kind.chunk_days, kind.max_inflight_reports, kind.max_creates_per_tick,
            kind.max_saves_per_tick) == (SbV2ReportFetcher, 1, 6, 6, 6)


def test_sp_search_terms_go_first_and_the_sb_ones_after_every_other_report():
    assert report_kinds.ALL[0] is report_kinds.SEARCH_TERMS
    assert report_kinds.ALL[-2:] == (report_kinds.SB_SEARCH_TERMS, report_kinds.SB_LEGACY_SEARCH_TERMS)
    assert {SB_SEARCH_TERMS_KIND, SB_LEGACY_SEARCH_TERMS_KIND} <= set(report_kinds.REPORT_JOB_KINDS)

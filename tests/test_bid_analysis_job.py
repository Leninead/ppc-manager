"""El análisis guardado del Bid Optimizer: su spec, su ventana y su payload."""
from datetime import date

import pandas as pd
import pytest

from ai import agent_call
from core.ai_analysis.bid_analysis_job import JOB_KIND, BidAnalysisSpec
from core.bid_analysis import (
    ANALYSIS_MODULE,
    CANONICAL_WINDOW_DAYS,
    BidAnalysisParams,
    build_analysis_input,
    canonical_analysis_window,
)
from core.search_term_frame import console_columns

ATTRIBUTION_DAYS = 7


def _frame(rows):
    frame = pd.DataFrame(rows)
    for column in console_columns(ATTRIBUTION_DAYS):
        if column not in frame.columns:
            frame[column] = 0
    return frame[console_columns(ATTRIBUTION_DAYS)]


def _row(campaign="DG - B0CYLMJJJC - SP - KW - EXACT - Core", clicks=100, spend=50.0, sales=200.0, orders=10):
    return {"Customer Search Term": "vitamin a cream", "Campaign Name": campaign, "Clicks": clicks,
            "Spend": spend, "7 Day Total Sales": sales, "7 Day Total Orders (#)": orders, "Impressions": 1000}


def _input(**overrides):
    options = {"frame": _frame([_row()]), "target_acos": 25, "account_label": "dermaglos · US",
               "period_label": "10 – 16 sep 2026", "currency_code": "USD"}
    options.update(overrides)
    return build_analysis_input(**options)


def test_the_job_kind_names_the_module_so_the_worker_claims_it():
    assert JOB_KIND == "ai_bid_optimizer_analysis"
    assert JOB_KIND.startswith("ai_")          # claim_ai_jobs filtra por 'ai\\_%'
    assert BidAnalysisSpec.module == ANALYSIS_MODULE


def test_the_canonical_window_is_the_seven_days_the_picker_opens_on():
    start, end = canonical_analysis_window(date(2026, 7, 11), date(2026, 9, 16))

    assert (end - start).days + 1 == CANONICAL_WINDOW_DAYS
    assert (start, end) == (date(2026, 9, 10), date(2026, 9, 16))


def test_a_short_history_clips_the_window_instead_of_asking_for_days_that_do_not_exist():
    assert canonical_analysis_window(date(2026, 9, 14), date(2026, 9, 16)) == (date(2026, 9, 14), date(2026, 9, 16))


def test_the_payload_carries_the_asins_and_their_records():
    analysis_input = _input()

    assert analysis_input.data is not None
    assert [record["asin"] for record in analysis_input.records] == ["B0CYLMJJJC"]
    assert analysis_input.data.target_acos == 25
    assert analysis_input.data.currency_code == "USD"


def test_an_empty_frame_has_nothing_to_analyze():
    assert _input(frame=_frame([])).data is None


def test_a_frame_whose_campaigns_carry_no_asin_has_nothing_to_analyze():
    analysis_input = _input(frame=_frame([_row(campaign="Campaña sin ASIN")]))

    assert analysis_input.data is None
    assert analysis_input.records == []


def test_the_same_data_and_target_digest_the_same_and_another_target_does_not():
    first = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data)
    same = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data)
    other = agent_call.build_agent_call(ANALYSIS_MODULE, _input(target_acos=40).data)

    assert first.input_digest == same.input_digest
    assert first.input_digest != other.input_digest


def test_the_period_label_is_part_of_the_payload_so_two_windows_never_share_an_analysis():
    first = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data)
    other = agent_call.build_agent_call(ANALYSIS_MODULE, _input(period_label="3 – 9 sep 2026").data)

    assert first.input_digest != other.input_digest


@pytest.mark.parametrize("values, expected", [
    ({}, 25),
    ({"target_acos": 40}, 40),
    ({"target_acos": "no es un número"}, 25),
])
def test_the_account_parameters_survive_a_broken_saved_value(values, expected):
    assert BidAnalysisParams.from_dict(values).target_acos == expected


def test_two_parameter_sets_with_the_same_target_share_a_digest():
    assert BidAnalysisParams(30).digest == BidAnalysisParams.from_dict({"target_acos": 30}).digest
    assert BidAnalysisParams(30).digest != BidAnalysisParams(31).digest


def test_the_spec_prepares_the_call_and_says_how_many_rows_travelled():
    class _Reports:
        @staticmethod
        def search_terms(profile, start, end):
            from core.search_term_frame import SearchTermSource
            return SearchTermSource(frame=_frame([_row()]), source="api", currency_code="USD",
                                    label="dermaglos · US", signature="sig", attribution_days=7, bulk_ready=True)

    prepared = BidAnalysisSpec.prepare(_Reports(), object(), BidAnalysisParams(25),
                                       date(2026, 9, 10), date(2026, 9, 16), "es")

    assert prepared.rows_written == 1
    assert list(prepared.record_columns) == ["records"]
    assert prepared.call.input_digest

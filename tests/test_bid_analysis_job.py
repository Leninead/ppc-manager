"""El análisis guardado del Bid Optimizer: su spec, su ventana y su payload."""
import pathlib
from datetime import date

import pandas as pd
import pytest

from ai import agent_call
from core.ai_analysis.bid_analysis_job import JOB_KIND, BidAnalysisSpec
from core.bid_optimizer.analysis import (
    ANALYSIS_MODULE,
    CANONICAL_WINDOW_DAYS,
    build_analysis_input,
    canonical_analysis_window,
)
from core.bid_optimizer.bids import BidAnalysisParams
from core.search_term.frame import console_columns

ATTRIBUTION_DAYS = 7


def _frame(rows):
    frame = pd.DataFrame(rows)
    for column in console_columns(ATTRIBUTION_DAYS):
        if column not in frame.columns:
            frame[column] = 0
    return frame[console_columns(ATTRIBUTION_DAYS)]


def _row(campaign="DG - B0CYLMJJJC - SP - KW - EXACT - Core", clicks=100, spend=50.0, sales=200.0, orders=10,
         match_type="EXACT"):
    return {"Customer Search Term": "vitamin a cream", "Campaign Name": campaign, "Match Type": match_type,
            "Clicks": clicks, "Spend": spend, "7 Day Total Sales": sales, "7 Day Total Orders (#)": orders,
            "Impressions": 1000}


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


def test_the_previous_stretch_travels_as_columns_and_is_announced_in_the_parameters():
    from ai.agents.bid_optimizer.context import build_context

    analysis_input = _input(previous_frame=_frame([_row(clicks=50, orders=2, sales=40.0, spend=30.0)]))
    _, docs, _ = build_context(analysis_input.data)

    assert analysis_input.records[0]["clicks_previo"] == 50
    assert analysis_input.records[0]["acos_previo"] == 75.0
    assert "columnas *_previo" in docs[0]["content"]


def test_without_a_previous_stretch_the_parameters_forbid_reading_a_trend():
    from ai.agents.bid_optimizer.context import build_context

    _, docs, _ = build_context(_input().data)

    assert "SIN PERÍODO ANTERIOR" in docs[0]["content"]
    assert "clicks_previo" not in docs[1]["content"]


def test_the_validated_spend_share_travels_when_the_frame_has_match_type():
    analysis_input = _input(frame=_frame([
        _row(campaign="DG - B0CYLMJJJC - SP - EXACT", spend=75.0, match_type="EXACT"),
        _row(campaign="DG - B0CYLMJJJC - SP - BROAD", spend=25.0, match_type="BROAD")]))

    # 75 de 100 del gasto corre sobre exact: eso es targeting ya validado, no descubrimiento.
    assert analysis_input.records[0]["pct_spend_validado"] == 75.0


def test_a_frame_without_match_type_says_nothing_instead_of_assuming_zero():
    frame = _frame([_row()]).drop(columns=["Match Type"])

    analysis_input = _input(frame=frame)

    assert "pct_spend_validado" not in analysis_input.records[0]


def test_the_clicks_median_of_the_document_reaches_the_parameters():
    from ai.agents.bid_optimizer.context import build_context, clicks_median

    assert clicks_median([{"clicks": 10}, {"clicks": 30}, {"clicks": 200}]) == 30
    assert clicks_median([]) == 0
    _, docs, _ = build_context(_input().data)
    assert "Mediana de clicks" in docs[0]["content"]


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


class _Profile:
    profile_id = "111"
    data_from = date(2026, 7, 1)


class _Reports:
    """Devuelve el mismo frame para cualquier ventana y anota qué ventanas le pidieron."""

    def __init__(self, frame=None):
        self.frame = frame if frame is not None else _frame([_row()])
        self.windows = []

    def search_terms(self, profile, start, end):
        from core.search_term.frame import SearchTermSource
        self.windows.append((start, end))
        return SearchTermSource(frame=self.frame, source="api", currency_code="USD",
                                label="dermaglos · US", signature="sig", attribution_days=7, bulk_ready=True)


def test_the_spec_prepares_the_call_and_says_how_many_rows_travelled():
    prepared = BidAnalysisSpec.prepare(_Reports(), _Profile(), BidAnalysisParams(25),
                                       date(2026, 9, 10), date(2026, 9, 16), "es")

    assert prepared.rows_written == 1
    assert list(prepared.record_columns) == ["records"]
    assert prepared.call.input_digest


def test_the_spec_also_reads_the_previous_stretch_of_the_same_length():
    reports = _Reports()

    BidAnalysisSpec.prepare(reports, _Profile(), BidAnalysisParams(25),
                            date(2026, 9, 10), date(2026, 9, 16), "es")

    assert reports.windows == [(date(2026, 9, 10), date(2026, 9, 16)),
                               (date(2026, 9, 3), date(2026, 9, 9))]


def test_an_account_whose_history_does_not_reach_back_is_not_asked_for_the_previous_stretch():
    reports = _Reports()

    class _Short(_Profile):
        data_from = date(2026, 9, 8)

    BidAnalysisSpec.prepare(reports, _Short(), BidAnalysisParams(25),
                            date(2026, 9, 10), date(2026, 9, 16), "es")

    assert reports.windows == [(date(2026, 9, 10), date(2026, 9, 16))]


def test_the_migration_lets_the_database_accept_this_module():
    """El RPC de la migración 010 tenía 'str' escrito a mano: un módulo nuevo recibía invalid_request."""
    migration = pathlib.Path("deploy/db/migrations/011_bid_optimizer_analysis.sql").read_text(encoding="utf-8")

    assert "ai_analysis_module_allowed" in migration
    assert "'str', 'bid_optimizer'" in migration
    # Los dos RPCs que llama la app dejan de comparar el módulo a mano.
    assert migration.count("not ai_analysis_module_allowed(p_module)") == 2
    assert "add column if not exists records" in migration


def test_a_refusal_the_page_cannot_translate_still_names_its_reason():
    from core.ai_analysis.stored_tab import REQUEST_REFUSED, REQUEST_REFUSED_UNKNOWN

    assert "migración" in REQUEST_REFUSED["invalid_request"]
    assert "motivo_nuevo" in REQUEST_REFUSED_UNKNOWN.format(reason="motivo_nuevo")

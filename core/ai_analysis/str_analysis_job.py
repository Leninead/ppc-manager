"""Search Term Report analyses: qué hace propio M2 sobre el esqueleto de core/ai_analysis/analysis_runner.

Planning is level-triggered: every tick compares each account's data version and saved parameters with the
last one it planned, and only then reads the report. A data version whose payload already has an analysis
(or a job generating it) costs nothing. Eso vive en AnalysisRunner; acá quedan la ventana canónica, los
parámetros de la cuenta y cómo se arma el payload del agente `str`.
"""
from __future__ import annotations

from ai.agent_call import build_agent_call
from core.ai_analysis.analysis_runner import (  # noqa: F401 — API del módulo, la usan worker y tests
    BACKGROUND_TIMEOUT_SECONDS,
    FAILED_BEFORE_NOTE,
    PROVIDER_GRACE_SECONDS,
    PROVIDER_RESPONSE_MARGIN_SECONDS,
    REUSED_WARNING,
    SCHEDULED_DEADLINE,
    SCHEDULED_MAX_ATTEMPTS,
    SUPERSEDED_WARNING,
    AnalysisJobError,
    AnalysisRunner,
    JobOutcome,
    PlanSummary,
    PreparedAnalysis,
)
from core.ai_analysis.store import AnalysisSettings, analysis_job_kind
from core.amazon_ads.report_provider import ProfileOption
from core.search_term.analysis import (
    ANALYSIS_MODULE,
    CANONICAL_LANG,
    build_analysis_input,
    canonical_analysis_window,
)
from core.search_term.candidates import StrAnalysisParams, add_metric_columns, detect_columns

JOB_KIND = analysis_job_kind(ANALYSIS_MODULE)
DATA_CHANGED_ERROR = ("Los datos de la cuenta cambiaron desde que se pidió el análisis. Cargá los datos nuevos en "
                      "el Search Term Report y pedilo de nuevo.")
NOTHING_TO_ANALYZE = "Con estos datos y parámetros no hay candidatos que analizar."


class StrAnalysisSpec:
    """Lo propio de M2: candidatos a negativizar y a harvest sobre el Search Term Report."""

    module = ANALYSIS_MODULE
    job_kind = JOB_KIND
    lang = CANONICAL_LANG
    data_changed_message = DATA_CHANGED_ERROR
    nothing_to_analyze_message = NOTHING_TO_ANALYZE

    @staticmethod
    def canonical_window(profile: ProfileOption):
        return canonical_analysis_window(profile.data_from, profile.data_through)

    @staticmethod
    def account_params(profile: ProfileOption, settings: AnalysisSettings | None) -> StrAnalysisParams:
        return (StrAnalysisParams.from_dict(settings.params, profile.currency_code) if settings
                else StrAnalysisParams.defaults(profile.currency_code))

    @staticmethod
    def params_from_dict(data: dict, currency_code: str) -> StrAnalysisParams:
        return StrAnalysisParams.from_dict(data, currency_code)

    @staticmethod
    def prepare(reports, profile, params, window_start, window_end, lang) -> PreparedAnalysis | None:
        source = reports.search_terms(profile, window_start, window_end)
        frame = source.frame
        if frame.empty:
            return None
        cols = detect_columns(frame)
        add_metric_columns(frame, cols)
        analysis_input = build_analysis_input(frame, cols, params, currency_code=source.currency_code, lang=lang)
        if analysis_input.data is None:
            return None
        return PreparedAnalysis(
            call=build_agent_call(ANALYSIS_MODULE, analysis_input.data),
            record_columns={"negative_records": analysis_input.negative_records,
                            "harvest_records": analysis_input.harvest_records},
            rows_written=len(analysis_input.negative_records) + len(analysis_input.harvest_records),
        )


class StrAnalysisJob(AnalysisRunner):
    def __init__(self, **kwargs):
        super().__init__(StrAnalysisSpec(), **kwargs)

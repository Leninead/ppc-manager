"""PPC Insights analyses: asked for from the page, never planned by the worker.

The same skeleton as M2 and M9 over analysis_runner, with two differences: nobody plans them, so an
account costs nothing until the AM asks, and the payload carries only what Amazon Ads syncs. The SQP,
the Business Report and the Campaign CSV are files the worker never sees.
"""
from __future__ import annotations

from ai.agent_call import build_agent_call
from core.ai_analysis.analysis_runner import AnalysisRunner, PreparedAnalysis
from core.ai_analysis.store import AnalysisSettings, analysis_job_kind
from core.amazon_ads.report_provider import ProfileOption
from core.date_labels import date_range_label
from core.ppc_insights.analysis import (
    ANALYSIS_MODULE,
    CANONICAL_LANG,
    InsightsAnalysisParams,
    build_analysis_input,
    canonical_analysis_window,
)

JOB_KIND = analysis_job_kind(ANALYSIS_MODULE)
DATA_CHANGED_ERROR = ("Los datos de la cuenta cambiaron desde que se pidió el análisis. Cargá los datos nuevos en "
                      "PPC Insights y pedilo de nuevo.")
NOTHING_TO_ANALYZE = "Con estos datos no hay nada que analizar: el período no tiene search terms."


class PpcInsightsAnalysisSpec:
    module = ANALYSIS_MODULE
    job_kind = JOB_KIND
    lang = CANONICAL_LANG
    on_demand = True
    data_changed_message = DATA_CHANGED_ERROR
    nothing_to_analyze_message = NOTHING_TO_ANALYZE

    @staticmethod
    def canonical_window(profile: ProfileOption):
        return canonical_analysis_window(profile.data_from, profile.data_through)

    @staticmethod
    def account_params(profile: ProfileOption, settings: AnalysisSettings | None) -> InsightsAnalysisParams:
        if settings is None:
            return InsightsAnalysisParams.defaults(profile.currency_code)
        return InsightsAnalysisParams.from_dict(settings.params, profile.currency_code)

    @staticmethod
    def params_from_dict(data: dict, currency_code: str) -> InsightsAnalysisParams:
        return InsightsAnalysisParams.from_dict(data, currency_code)

    @staticmethod
    def prepare(reports, profile, params, window_start, window_end, lang) -> PreparedAnalysis | None:
        source = reports.search_terms(profile, window_start, window_end)
        analysis_input = build_analysis_input(
            source.frame, params=params, account_label=source.label,
            period_label=date_range_label(window_start, window_end), currency_code=source.currency_code,
            lang=lang, ad_group_asins=reports.advertised_asins(profile.profile_id))
        if analysis_input.data is None:
            return None
        return PreparedAnalysis(
            call=build_agent_call(ANALYSIS_MODULE, analysis_input.data),
            record_columns={"records": analysis_input.records},
            rows_written=len(analysis_input.records),
        )


class PpcInsightsAnalysisJob(AnalysisRunner):
    def __init__(self, **kwargs):
        super().__init__(PpcInsightsAnalysisSpec(), **kwargs)

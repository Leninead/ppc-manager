"""Bid Optimizer analyses: lo propio del módulo sobre el esqueleto de analysis_runner.

Mismo ciclo que M2 — se planifica cuando cambian los datos o el target ACoS de la cuenta, se
encola, lo corre el worker y queda guardado por huella — con un payload más chico: una fila por
ASIN con su bid ya calculado, más los placements por campaña.
"""
from __future__ import annotations

from ai.agent_call import build_agent_call
from core.ai_analysis.analysis_runner import AnalysisRunner, PreparedAnalysis
from core.ai_analysis.store import AnalysisSettings, analysis_job_kind
from core.amazon_ads.report_provider import ProfileOption, ReportReadError
from core.bid_analysis import (
    ANALYSIS_MODULE,
    CANONICAL_LANG,
    BidAnalysisParams,
    build_analysis_input,
    canonical_analysis_window,
    previous_window,
)
from core.date_labels import date_range_label

JOB_KIND = analysis_job_kind(ANALYSIS_MODULE)
DATA_CHANGED_ERROR = ("Los datos de la cuenta cambiaron desde que se pidió el análisis. Cargá los datos nuevos en "
                      "el Bid Optimizer y pedilo de nuevo.")
NOTHING_TO_ANALYZE = ("Con estos datos no hay ASINs que analizar: el reporte no trae el ASIN anunciado y ningún "
                      "nombre de campaña del período contiene uno.")


class BidAnalysisSpec:
    module = ANALYSIS_MODULE
    job_kind = JOB_KIND
    lang = CANONICAL_LANG
    data_changed_message = DATA_CHANGED_ERROR
    nothing_to_analyze_message = NOTHING_TO_ANALYZE

    @staticmethod
    def canonical_window(profile: ProfileOption):
        return canonical_analysis_window(profile.data_from, profile.data_through)

    @staticmethod
    def account_params(profile: ProfileOption, settings: AnalysisSettings | None) -> BidAnalysisParams:
        return BidAnalysisParams.from_dict(settings.params) if settings else BidAnalysisParams.defaults()

    @staticmethod
    def params_from_dict(data: dict, currency_code: str) -> BidAnalysisParams:
        # El target ACoS no depende de la moneda; la firma la fija el runner, que sí la necesita en M2.
        return BidAnalysisParams.from_dict(data)

    @staticmethod
    def prepare(reports, profile, params, window_start, window_end, lang) -> PreparedAnalysis | None:
        source = reports.search_terms(profile, window_start, window_end)
        analysis_input = build_analysis_input(
            source.frame, target_acos=params.target_acos, account_label=source.label,
            period_label=date_range_label(window_start, window_end),
            currency_code=source.currency_code, lang=lang,
            previous_frame=_previous_frame(reports, profile, window_start, window_end))
        if analysis_input.data is None:
            return None
        return PreparedAnalysis(
            call=build_agent_call(ANALYSIS_MODULE, analysis_input.data),
            record_columns={"records": analysis_input.records},
            rows_written=len(analysis_input.records),
        )


def _previous_frame(reports, profile, window_start, window_end):
    """El tramo anterior, o None si la cuenta no llega tan atrás o no se pudo leer.

    Falta de historial no es un error: el payload viaja sin comparación y el prompt no la insinúa.
    """
    start, end = previous_window(window_start, window_end)
    if profile.data_from is not None and start < profile.data_from:
        return None
    try:
        return reports.search_terms(profile, start, end).frame
    except ReportReadError:
        return None


class BidAnalysisJob(AnalysisRunner):
    def __init__(self, **kwargs):
        super().__init__(BidAnalysisSpec(), **kwargs)

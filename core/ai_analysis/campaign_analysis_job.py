"""Bulk Campañas analyses: what is M6's own on top of the analysis_runner skeleton.

Same cycle as the other modules — planned when the account's data or parameters change, queued,
run by the worker and stored by fingerprint — over a different grain: the campaign sync, which
does not write ads_profile_sync. So its window, day and hour come from the last completed
`sp_campaigns` request, and a request still rewriting days holds the planning back. The payload
reads SB and SD campaigns too, so their campaign requests hold it back and plan it again as well.
"""
from __future__ import annotations

import dataclasses

from ai.agent_call import build_agent_call
from core.ai_analysis.analysis_runner import AnalysisRunner, PreparedAnalysis
from core.ai_analysis.store import AnalysisSettings, analysis_job_kind
from core.amazon_ads.campaign_analyzer import CampaignAnalyzerParams
from core.amazon_ads.campaign_provider import CampaignProvider, campaign_sync_view
from core.amazon_ads.product_provider import ProductProvider
from core.amazon_ads.report_provider import ProfileOption
from core.amazon_ads.sync_planner import CAMPAIGNS_KIND, PRODUCT_CAMPAIGN_KINDS
from core.bulk_campaigns.analysis import ANALYSIS_MODULE, CANONICAL_LANG, build_analysis_input, canonical_analysis_window
from core.date_labels import date_range_label

JOB_KIND = analysis_job_kind(ANALYSIS_MODULE)
DATA_CHANGED_ERROR = ("Las campañas de la cuenta cambiaron desde que se pidió el análisis. Recargá Bulk Campañas "
                      "y pedilo de nuevo.")
NOTHING_TO_ANALYZE = "Esta cuenta no tiene campañas habilitadas con métricas para analizar en este período."


class CampaignAnalysisSpec:
    module = ANALYSIS_MODULE
    job_kind = JOB_KIND
    lang = CANONICAL_LANG
    source_job_kind = CAMPAIGNS_KIND
    source_job_kinds = (CAMPAIGNS_KIND, *PRODUCT_CAMPAIGN_KINDS)
    data_changed_message = DATA_CHANGED_ERROR
    nothing_to_analyze_message = NOTHING_TO_ANALYZE

    def __init__(self, campaigns: CampaignProvider, products: ProductProvider):
        self._campaigns = campaigns
        self._products = products

    @staticmethod
    def data_view(profile: ProfileOption, jobs) -> ProfileOption:
        """The SP campaign sync's window; its last success moves forward when SB or SD data arrive later."""
        view = campaign_sync_view(profile, jobs.latest_completed_for_profile(profile.profile_id, CAMPAIGNS_KIND))
        if view.data_through is None:
            return view
        products = jobs.latest_completed_of_kinds(profile.profile_id, PRODUCT_CAMPAIGN_KINDS)
        finished_at = products.finished_at if products is not None else None
        if finished_at is None or (view.last_success_at is not None and finished_at <= view.last_success_at):
            return view
        return dataclasses.replace(view, last_success_at=finished_at)

    @staticmethod
    def canonical_window(profile: ProfileOption):
        return canonical_analysis_window(profile.data_from, profile.data_through)

    @staticmethod
    def account_params(profile: ProfileOption, settings: AnalysisSettings | None) -> CampaignAnalyzerParams:
        return CampaignAnalyzerParams.from_dict(settings.params) if settings else CampaignAnalyzerParams.defaults()

    @staticmethod
    def params_from_dict(data: dict, currency_code: str) -> CampaignAnalyzerParams:
        return CampaignAnalyzerParams.from_dict(data)

    def prepare(self, reports, profile, params, window_start, window_end, lang) -> PreparedAnalysis | None:
        source = self._campaigns.campaigns(profile, window_start, window_end)
        products = self._products.campaigns(profile.profile_id, window_start, window_end)
        analysis_input = build_analysis_input(
            source.frame, signal_inputs=source.signal_inputs, params=params, account_label=source.label,
            period_label=date_range_label(window_start, window_end), currency_code=source.currency_code,
            attribution_days=source.attribution_days, window_start=window_start, window_end=window_end, lang=lang,
            products=products)
        if analysis_input.data is None:
            return None
        return PreparedAnalysis(
            call=build_agent_call(ANALYSIS_MODULE, analysis_input.data),
            record_columns={"records": analysis_input.records},
            rows_written=len(analysis_input.records),
        )


class CampaignAnalysisJob(AnalysisRunner):
    def __init__(self, **kwargs):
        rest = kwargs["reports"].rest
        super().__init__(CampaignAnalysisSpec(CampaignProvider(rest), ProductProvider(rest)), **kwargs)

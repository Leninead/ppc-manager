"""PPC Insights analyses on the worker: asked for from the page, never planned, and never paid twice per version."""
from datetime import date, timedelta

import pandas as pd

from ai import agent_call
from core.ai_analysis.ppc_insights_analysis_job import JOB_KIND, PpcInsightsAnalysisJob, PpcInsightsAnalysisSpec
from core.ai_analysis.store import AiAnalysisStore
from core.ai_analysis.worker import build_jobs
from core.integrations.sync_jobs import SyncJob, SyncJobStore
from core.ppc_insights.analysis import ANALYSIS_MODULE, build_analysis_input
from core.ppc_insights.asin_health import InsightsAnalysisParams
from core.search_term.frame import SOURCE_API, SearchTermSource, console_columns
from tests.test_str_analysis_job import NOW, FakeRest, _profile

WINDOW = (date(2026, 9, 8), date(2026, 9, 14))
MAPPING = {"AG1": frozenset({"B0CYLMJJJC"})}
RESULT = {"asins": [], "synthesis": {"situation": "s", "week_actions": [], "mid_term": [], "risks": [],
                                     "executive_summary": "e"}}
PARAMS = {"target_acos": 25, "price": 15.0}


def _search_frame():
    frame = pd.DataFrame([{"Customer Search Term": "vitamin a cream", "Campaign Name": "DG - SP - KW",
                           "_ad_group_id": "AG1", "Spend": 20.0, "7 Day Total Sales": 80.0,
                           "7 Day Total Orders (#)": 4, "Clicks": 30, "Impressions": 900}])
    for column in console_columns(7):
        if column not in frame.columns:
            frame[column] = 0
    return frame[console_columns(7) + ["_ad_group_id"]]


class FakeReports:
    def __init__(self, profiles):
        self._profiles = profiles

    def profiles(self):
        return list(self._profiles)

    def search_terms(self, option, start, end):
        return SearchTermSource(frame=_search_frame(), source=SOURCE_API, currency_code=option.currency_code,
                                label=option.label, signature="sig", attribution_days=7, bulk_ready=True,
                                profile_id=option.profile_id, window_start=start, window_end=end)

    def advertised_asins(self, profile_id):
        return dict(MAPPING)


def _page_call(params=PARAMS):
    """The agent call the page builds for the same data: the digest the worker must reproduce."""
    source = FakeReports([_profile()]).search_terms(_profile(), *WINDOW)
    analysis_input = build_analysis_input(
        source.frame, params=InsightsAnalysisParams.from_dict(params, "USD"), account_label=source.label,
        period_label="8 – 14 sep 2026", currency_code="USD", ad_group_asins=MAPPING)
    return agent_call.build_agent_call(ANALYSIS_MODULE, analysis_input.data)


def _job(fake, job_id=9, agent_version=""):
    params = {"lang": "es", "input_digest": _page_call().input_digest, "params": dict(PARAMS)}
    if agent_version:
        params["agent_version"] = agent_version
    row = {"id": job_id, "integration_slug": "amazon_ads", "job_kind": JOB_KIND, "trigger": "manual",
           "external_account_id": "111", "status": "running", "attempts": 0, "max_attempts": 3,
           "window_start": WINDOW[0].isoformat(), "window_end": WINDOW[1].isoformat(), "requested_by": "ana",
           "deadline_at": (NOW + timedelta(hours=6)).isoformat(), "params": params}
    fake.tables["integration_sync_jobs"].append(row)
    return SyncJob.from_row(row)


def _runner(fake, calls):
    def ask(**call):
        calls.append(call)
        return {"structured_output": RESULT, "session_id": "s", "request_id": "r", "usage": {}}
    return PpcInsightsAnalysisJob(store=AiAnalysisStore(fake), jobs=SyncJobStore(fake),
                                  reports=FakeReports([_profile()]), ask=ask, clock=lambda: NOW)


def test_the_job_kind_names_the_module_and_the_worker_dispatches_it():
    assert JOB_KIND == "ai_ppc_insights_analysis"
    assert JOB_KIND in build_jobs(FakeRest())


def test_nobody_plans_it_so_new_data_costs_nothing_until_the_am_asks():
    fake = FakeRest()

    summary = _runner(fake, []).plan()

    assert fake.tables["integration_sync_jobs"] == [] and summary.analyses_queued == 0
    assert PpcInsightsAnalysisSpec.on_demand


def test_the_worker_builds_the_digest_the_page_asked_for_and_stores_its_rows():
    fake, calls = FakeRest(), []

    outcome = _runner(fake, calls).execute(_job(fake))

    stored = fake.tables["ai_analyses"][0]
    assert len(calls) == 1 and outcome.analysis_id == stored["id"]
    assert stored["input_digest"] == _page_call().input_digest
    assert stored["records"][0]["asin"] == "B0CYLMJJJC"


def test_data_already_analyzed_by_this_version_is_not_paid_again():
    fake, calls = FakeRest(), []
    _runner(fake, calls).execute(_job(fake, job_id=8))

    outcome = _runner(fake, calls).execute(_job(fake, job_id=9, agent_version=_page_call().agent_version))

    assert outcome.reused and len(calls) == 1


def test_recalculating_data_an_older_version_analyzed_calls_the_ai_again():
    fake, calls = FakeRest(), []
    _runner(fake, calls).execute(_job(fake, job_id=8))
    fake.tables["ai_analyses"][0]["agent_version"] = "an older prompt"

    outcome = _runner(fake, calls).execute(_job(fake, job_id=9, agent_version=_page_call().agent_version))

    assert not outcome.reused and len(calls) == 2
    assert {row["agent_version"] for row in fake.tables["ai_analyses"]} == {"an older prompt",
                                                                            _page_call().agent_version}


MIGRATION = __import__("pathlib").Path("deploy/db/migrations/017_ppc_insights.sql").read_text(encoding="utf-8")


def test_the_migration_keeps_the_product_ads_the_worker_writes_and_the_app_and_analysis_worker_read():
    assert "create table if not exists ads_product_ad" in MIGRATION
    assert "primary key (profile_id, ad_id)" in MIGRATION
    assert "on ads_product_ad (profile_id, ad_group_id)" in MIGRATION
    assert "grant select on ads_product_ad to web_user;" in MIGRATION
    assert "grant select on ads_product_ad to ai_worker;" in MIGRATION
    assert "grant select, insert, update, delete on ads_product_ad to integ_worker;" in MIGRATION


def test_the_migration_allows_the_module_and_replaces_the_request_function_instead_of_overloading_it():
    assert "select p_module in ('str', 'bid_optimizer', 'bulk_campaigns', 'ppc_insights')" in MIGRATION
    assert "drop function if exists request_ai_analysis(text, text, date, date, text, jsonb, text, text);" in MIGRATION
    assert "p_agent_version text default ''" in MIGRATION
    assert ("grant execute on function request_ai_analysis(text, text, date, date, text, jsonb, text, text, text) "
            "to web_user;") in MIGRATION
    assert "and (wanted_version = '' or analysis.agent_version = wanted_version)" in MIGRATION
    assert MIGRATION.rstrip().endswith("notify pgrst, 'reload schema';")


class _RecordingRest:
    def __init__(self):
        self.calls = []

    def rpc(self, name, args, **_):
        self.calls.append(args)
        return [{"job_id": 1, "created": True, "reason": "created"}]


def test_the_store_names_the_prompt_version_only_when_the_page_asks_for_it():
    fake = _RecordingRest()
    store = AiAnalysisStore(fake)
    request = dict(window_start=WINDOW[0], window_end=WINDOW[1], lang="es", params=PARAMS, input_digest="d",
                   requested_by="ana")

    store.request_analysis(ANALYSIS_MODULE, "111", **request)
    store.request_analysis(ANALYSIS_MODULE, "111", **request, agent_version="v-now")

    assert "p_agent_version" not in fake.calls[0]
    assert fake.calls[1]["p_agent_version"] == "v-now"

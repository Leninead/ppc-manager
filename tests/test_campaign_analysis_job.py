"""Stored Bulk Campañas analyses: the payload the agent reads, its fingerprint, and planning over the campaign
sync — which does not write ads_profile_sync, so its window, day and hour come from its own requests."""
import csv
import io
import json
from datetime import date, datetime, timezone

import pandas as pd

from ai import agent_call
from ai.agents.bulk_campaigns.context import CAMPAIGN_PREFIX, build_context
from core.ai_analysis.campaign_analysis_job import JOB_KIND, CampaignAnalysisJob, CampaignAnalysisSpec
from core.ai_analysis.store import AiAnalysisStore
from core.amazon_ads.campaign_analyzer import CampaignAnalyzerParams
from core.amazon_ads.campaign_provider import SIGNAL_COLUMNS, CampaignProvider
from core.amazon_ads.product_provider import ProductCampaigns, ProductProvider
from core.amazon_ads.report_provider import ProfileOption
from core.campaign_analysis import (
    ANALYSIS_MODULE,
    CANONICAL_WINDOW_DAYS,
    build_analysis_input,
    campaign_row_labels,
    canonical_analysis_window,
)
from core.integrations.sync_jobs import SyncJobStore

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
WINDOW = (date(2026, 9, 10), date(2026, 9, 16))
PARAMS = CampaignAnalyzerParams(35.0, 20.0, 2)
RPC_HEADER = ["campaign_id", "name", "state", "targeting_type", "start_date", "budget_amount", "budget_type",
              "bidding_strategy", "portfolio_id", "portfolio_name", "impressions", "clicks", "cost",
              "purchases_7d", "sales_7d", "purchases_14d", "sales_14d", "currency_code",
              "budget_capped_days", "days_with_impressions", "top_of_search_is"]


def _campaign(campaign_id, name, *, impressions=1000, clicks=20, cost=10.0, orders=2, sales=100.0, state="ENABLED",
              budget=30.0):
    return {"Campaign name": name, "Campaign ID": campaign_id, "State": state, "Type": "Sponsored Products",
            "Portfolio name": "", "Campaign start date": "2026-03-01", "Campaign bid strategy": "MANUAL",
            "Campaign budget amount": budget, "Impressions": impressions, "Clicks": clicks,
            "CTR": clicks / impressions if impressions else float("nan"), "Total cost": cost,
            "CPC": cost / clicks if clicks else float("nan"), "Purchases": orders, "Sales": sales,
            "ACOS": cost / sales if sales else float("nan"), "ROAS": sales / cost if cost else float("nan")}


def _signal(campaign_id, *, capped=0, start=date(2026, 3, 1), share=25.0):
    return {"Campaign ID": campaign_id, "start_date": start, "budget_type": "DAILY", "budget_capped_days": capped,
            "days_with_impressions": 7, "top_of_search_is": share}


CAMPAIGNS = [
    _campaign("1", "Alpha ok", cost=30.0, orders=1, sales=100.0),
    _campaign("2", "Beta bleeder", cost=25.0, orders=0, sales=0.0),
    _campaign("3", "Gamma ghost", impressions=0, clicks=0, cost=0.0, orders=0, sales=0.0),
    _campaign("4", "Delta big ok", cost=60.0, orders=3, sales=200.0),
]


def _input(campaigns=CAMPAIGNS, signals=None, **overrides):
    frame = pd.DataFrame(campaigns)
    signal_inputs = (pd.DataFrame(signals if signals is not None else [_signal(row["Campaign ID"]) for row in campaigns],
                                  columns=list(SIGNAL_COLUMNS)) if signals is not False else None)
    options = {"signal_inputs": signal_inputs, "params": PARAMS, "account_label": "dermaglos · US",
               "period_label": "10 – 16 sep 2026", "currency_code": "USD", "attribution_days": 7,
               "window_start": WINDOW[0], "window_end": WINDOW[1]}
    options.update(overrides)
    return build_analysis_input(frame, **options)


class TestPayload:
    def test_the_job_kind_names_the_module_so_the_worker_claims_it(self):
        assert JOB_KIND == "ai_bulk_campaigns_analysis" and JOB_KIND.startswith("ai_")
        assert CampaignAnalysisSpec.module == ANALYSIS_MODULE == "bulk_campaigns"

    def test_the_canonical_window_is_the_seven_days_the_picker_opens_on(self):
        start, end = canonical_analysis_window(date(2026, 7, 14), date(2026, 9, 16))

        assert (end - start).days + 1 == CANONICAL_WINDOW_DAYS and (start, end) == WINDOW

    def test_campaigns_with_something_to_say_come_first_and_then_by_spend(self):
        records = _input().records

        # Beta is PAUSAR, Gamma FANTASMA; the two OK ones follow, the bigger spender first.
        assert [record["campaign"] for record in records] == ["Beta bleeder", "Gamma ghost", "Delta big ok",
                                                              "Alpha ok"]

    def test_a_signal_is_enough_to_come_first(self):
        records = _input(signals=[_signal("1", capped=4), _signal("2"), _signal("3"), _signal("4")]).records

        # Alpha is OK but held back by its budget: it joins the flagged ones, which go by spend (30 > 25 > 0).
        assert [record["campaign"] for record in records] == ["Alpha ok", "Beta bleeder", "Gamma ghost",
                                                              "Delta big ok"]
        assert records[0]["senales"] == "Limitada por presupuesto"

    def test_the_records_are_plain_json_with_empty_ratios_where_there_is_no_base(self):
        records = _input().records

        json.dumps(records)          # NaN or numpy types would break the stored analysis
        ghost = next(record for record in records if record["campaign"] == "Gamma ghost")
        assert (ghost["acos"], ghost["cpc"], ghost["ctr"]) == (None, None, None)
        assert ghost["diagnostico"] == "FANTASMA"

    def test_without_signal_inputs_the_rows_carry_no_signal_fields_and_parameters_say_so(self):
        analysis_input = _input(signals=False)
        _, docs, _ = build_context(analysis_input.data)

        assert "tos_is" not in analysis_input.records[0]
        assert "SIN SEÑALES" in docs[0]["content"]

    def test_the_parameters_carry_the_counts_the_pause_spend_and_the_provisional_days(self):
        _, docs, _ = build_context(_input().data)
        params = docs[0]["content"]

        assert "FANTASMA 1, PAUSAR 1, REVISAR 0, ESCALAR 0, OK 2" in params
        assert "Gasto de las campañas en PAUSAR (sin órdenes en el período): 25" in params
        assert "Días provisorios: 2026-09-15, 2026-09-16" in params
        assert "Target ACoS: 35%" in params

    def test_the_document_names_its_rows_with_the_campaign_prefix(self):
        analysis_input = _input()
        _, docs, _ = build_context(analysis_input.data)

        assert docs[1]["content"].splitlines()[1].startswith(f"{CAMPAIGN_PREFIX}01,")
        assert "\r" not in docs[1]["content"]
        assert campaign_row_labels(analysis_input.records)["C02"] == "Gamma ghost"

    def test_a_long_account_is_capped_and_the_parameters_say_how_many_stayed_out(self):
        many = [_campaign(str(index), f"C{index:03d}", cost=float(index)) for index in range(1, 71)]

        analysis_input = _input(campaigns=many)
        _, docs, _ = build_context(analysis_input.data)

        assert len(analysis_input.records) == 60
        assert "Quedaron 10 campañas fuera del documento" in docs[0]["content"]

    def test_the_same_campaigns_and_parameters_fingerprint_the_same_and_other_parameters_do_not(self):
        first = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data)
        same = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data)
        other = agent_call.build_agent_call(ANALYSIS_MODULE, _input(params=CampaignAnalyzerParams(40, 20, 2)).data)

        assert first.input_digest == same.input_digest != other.input_digest

    def test_an_account_without_enabled_campaigns_has_nothing_to_analyze(self):
        assert _input(campaigns=[_campaign("1", "Paused", state="PAUSED")]).data is None

    def test_a_file_without_the_performance_columns_has_nothing_to_analyze(self):
        frame = pd.DataFrame([{"Campaign name": "Alpha", "State": "ENABLED"}])

        assert build_analysis_input(frame, signal_inputs=None, params=PARAMS, account_label="x", period_label="",
                                    currency_code="", attribution_days=7, window_start=WINDOW[0],
                                    window_end=WINDOW[1]).data is None


def _products(*rows, without=()):
    """SB / SD campaigns as ProductProvider hands them: the export's columns plus the click-only ones."""
    frame = pd.DataFrame([{**_campaign(campaign_id, name, cost=cost, orders=orders, sales=sales),
                           "Type": product_type, "Purchases (clicks)": orders_clicks, "Sales (clicks)": sales_clicks}
                          for campaign_id, name, product_type, cost, orders, sales, orders_clicks, sales_clicks in rows])
    return ProductCampaigns(frame=frame, without_metrics=frozenset(without))


SB_AND_SD = _products(("701", "Brand video", "Sponsored Brands", 40.0, 4, 300.0, 1, 90.0),
                      ("801", "Display views", "Sponsored Display", 22.0, 0, 0.0, 0, 0.0),
                      ("702", "Brand legacy", "Sponsored Brands", 0.0, 0, 0.0, 0, 0.0), without={"702"})


class TestThreeProducts:
    def test_sb_and_sd_campaigns_join_the_document_with_their_product_and_click_only_sales(self):
        records = {record["campaign"]: record for record in _input(products=SB_AND_SD).records}

        assert {name: record["producto"] for name, record in records.items()} == {
            "Beta bleeder": "SP", "Gamma ghost": "SP", "Delta big ok": "SP", "Alpha ok": "SP",
            "Brand video": "SB", "Display views": "SD"}
        assert (records["Brand video"]["sales"], records["Brand video"]["sales_clicks"]) == (300.0, 90.0)
        assert (records["Alpha ok"]["sales_clicks"], records["Alpha ok"]["orders_clicks"]) == (100.0, 1)
        # Diagnosed like SP, with the sales Campaign Manager shows: 22 spent and no order is a pause.
        assert records["Display views"]["diagnostico"] == "PAUSAR"

    def test_an_sb_campaign_without_metrics_stays_out_and_the_parameters_say_so(self):
        analysis_input = _input(products=SB_AND_SD)
        _, docs, _ = build_context(analysis_input.data)
        params = docs[0]["content"]

        assert "Brand legacy" not in [record["campaign"] for record in analysis_input.records]
        assert "Por producto: SP 4, SB 1, SD 1." in params
        assert "Campañas SB habilitadas del formato anterior sin métricas en la API: 1" in params
        assert "SB y SD, 14 días con clicks o vistas" in params

    def test_an_account_with_only_sp_reads_exactly_as_before(self):
        only_sp = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data)
        no_products = agent_call.build_agent_call(ANALYSIS_MODULE, _input(products=_products()).data)
        _, docs, _ = build_context(_input().data)

        assert "producto" not in _input().records[0]
        assert "Por producto" not in docs[0]["content"] and "SB y SD" not in docs[0]["content"]
        assert only_sp.input_digest == no_products.input_digest

    def test_the_chat_reads_the_product_of_each_campaign_the_analysis_cites(self):
        from ai.agents.bulk_campaigns import chat_document

        records = _input(products=SB_AND_SD).records
        row_id = next(f"C{index + 1:02d}" for index, record in enumerate(records) if record["producto"] == "SD")
        result = {"synthesis": {"situation": "x"}, "campaigns": [
            {"row_id": row_id, "razon": "gastó sin vender", "causa": "SIN_CONVERSION", "veredicto": "ACTUAR",
             "confianza": "media", "advertencia": None}]}

        text = chat_document.reading_text(result, records)

        assert f"{row_id} · Display views (SD · PAUSAR, gasto 22.0, sin ventas)" in text

    def test_sb_or_sd_data_that_changes_changes_the_fingerprint(self):
        before = agent_call.build_agent_call(ANALYSIS_MODULE, _input(products=SB_AND_SD).data)
        after = agent_call.build_agent_call(ANALYSIS_MODULE, _input(products=_products(
            ("701", "Brand video", "Sponsored Brands", 45.0, 4, 300.0, 1, 90.0))).data)

        assert before.input_digest != after.input_digest


# ── the spec and the runner over the campaign sync ────────────────────────────


class FakeRest:
    """In-memory PostgREST: the analysis tables, the sync jobs and campaigns_between."""

    def __init__(self, campaign_rows=()):
        self.tables = {"ai_analyses": [], "ai_analysis_settings": [], "integration_sync_jobs": []}
        self.campaign_rows = list(campaign_rows)
        self.campaign_reads = []
        self._next_id = 100

    @staticmethod
    def _matches(row, params):
        for column, condition in params.items():
            if column in ("select", "order", "limit", "on_conflict"):
                continue
            value = (row.get("params") or {}).get("input_digest") if column == "params->>input_digest" \
                else row.get(column)
            operator, _, expected = condition.partition(".")
            if operator == "eq" and str(value) != expected:
                return False
            if operator == "in" and str(value) not in expected.strip("()").split(","):
                return False
        return True

    def select(self, table, params):
        rows = [dict(row) for row in self.tables[table] if self._matches(row, params)]
        return rows[:int(params["limit"])] if "limit" in params else rows

    def insert_returning(self, table, row, **_):
        self._next_id += 1
        stored = {**row, "id": self._next_id}
        self.tables[table].append(stored)
        return stored

    def insert_ignore(self, table, row, on_conflict, **_):
        if any(existing.get(on_conflict) == row.get(on_conflict) for existing in self.tables[table]):
            return False
        self.insert_returning(table, {"status": "pending", "attempts": 0, **row})
        return True

    def rpc_csv(self, name, args, **_):
        if name == "product_campaigns_between":
            # SB / SD (migration 015): none unless a test gives them.
            return b""
        assert name == "campaigns_between"
        self.campaign_reads.append((args["p_from"], args["p_to"]))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=RPC_HEADER)
        writer.writeheader()
        writer.writerows(self.campaign_rows)
        return buffer.getvalue().encode("utf-8")


class FakeReports:
    def __init__(self, rest, profiles):
        self.rest = rest
        self._profiles = profiles

    def profiles(self):
        return list(self._profiles)


def _rpc_campaign(campaign_id, name, cost, orders, sales):
    return {"campaign_id": campaign_id, "name": name, "state": "ENABLED", "targeting_type": "MANUAL",
            "start_date": "2026-03-01", "budget_amount": "30", "budget_type": "DAILY", "bidding_strategy": "MANUAL",
            "portfolio_id": "", "portfolio_name": "", "impressions": "1000", "clicks": "20", "cost": str(cost),
            "purchases_7d": str(orders), "sales_7d": str(sales), "purchases_14d": str(orders),
            "sales_14d": str(sales), "currency_code": "USD", "budget_capped_days": "0",
            "days_with_impressions": "7", "top_of_search_is": "12.5"}


def _profile(**overrides):
    # The search-term sync says data ends on the 14th; the campaign sync, on the 16th.
    row = {"profile_id": "111", "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids US",
           "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "America/Los_Angeles",
           "status": "active", "data_from": "2026-07-11", "data_through": "2026-09-14", "refreshed_on": "2026-09-15",
           "last_success_at": "2026-09-15T10:00:00+00:00", "last_error": ""}
    row.update(overrides)
    return ProfileOption.from_row(row)


def _campaign_job(fake, *, status="completed", job_id=441, kind="sp_campaigns",
                  finished_at="2026-09-18T00:51:00+00:00"):
    fake.tables["integration_sync_jobs"].append({
        "id": job_id, "integration_slug": "amazon_ads", "job_kind": kind, "trigger": "scheduled_daily",
        "external_account_id": "111", "status": status, "attempts": 0, "max_attempts": 6,
        "window_start": "2026-07-14", "window_end": "2026-09-16", "local_day": "2026-09-17",
        "finished_at": finished_at if status == "completed" else None,
        "created_at": "2026-09-18T00:43:00+00:00"})


def _runner(fake, profiles):
    return CampaignAnalysisJob(store=AiAnalysisStore(fake), jobs=SyncJobStore(fake), reports=FakeReports(fake, profiles),
                               ask=lambda **call: {"structured_output": {}}, clock=lambda: NOW)


class TestSpecAndPlanning:
    def test_the_view_takes_window_day_and_hour_from_the_last_completed_campaign_request(self):
        fake = FakeRest()
        _campaign_job(fake)

        view = CampaignAnalysisSpec.data_view(_profile(), SyncJobStore(fake))

        assert (view.data_from, view.data_through) == (date(2026, 7, 14), date(2026, 9, 16))
        assert view.last_success_at == datetime(2026, 9, 18, 0, 51, tzinfo=timezone.utc)

    def test_new_campaign_data_queues_one_analysis_of_the_campaign_window_not_the_search_term_one(self):
        fake = FakeRest([_rpc_campaign("1", "Alpha", 25.0, 0, 0.0), _rpc_campaign("2", "Beta", 10.0, 2, 100.0)])
        _campaign_job(fake)

        summary = _runner(fake, [_profile()]).plan()

        queued = [job for job in fake.tables["integration_sync_jobs"] if job["job_kind"] == JOB_KIND]
        assert summary.analyses_queued == 1 and len(queued) == 1
        assert (queued[0]["window_start"], queued[0]["window_end"]) == ("2026-09-10", "2026-09-16")
        assert fake.campaign_reads == [("2026-09-10", "2026-09-16")]

    def test_an_account_the_campaign_sync_never_completed_is_skipped(self):
        fake = FakeRest([_rpc_campaign("1", "Alpha", 25.0, 0, 0.0)])

        summary = _runner(fake, [_profile()]).plan()

        assert summary.profiles_checked == 0 and summary.analyses_queued == 0

    def test_while_a_campaign_request_rewrites_days_the_planning_waits(self):
        fake = FakeRest([_rpc_campaign("1", "Alpha", 25.0, 0, 0.0)])
        _campaign_job(fake)
        _campaign_job(fake, status="running", job_id=442)

        summary = _runner(fake, [_profile()]).plan()

        assert summary.analyses_queued == 0 and fake.campaign_reads == []

    def test_the_spec_prepares_the_call_and_says_how_many_rows_travelled(self):
        fake = FakeRest([_rpc_campaign("1", "Alpha", 25.0, 0, 0.0), _rpc_campaign("2", "Beta", 10.0, 2, 100.0)])
        spec = CampaignAnalysisSpec(CampaignProvider(fake), ProductProvider(fake))

        prepared = spec.prepare(None, _profile(), PARAMS, *WINDOW, "es")

        assert prepared.rows_written == 2 and list(prepared.record_columns) == ["records"]
        assert prepared.call.input_digest

    def test_sb_or_sd_data_that_arrives_later_moves_the_view_so_the_analysis_is_planned_again(self):
        fake = FakeRest()
        _campaign_job(fake)
        _campaign_job(fake, job_id=443, kind="sb_campaigns", finished_at="2026-09-18T02:10:00+00:00")

        view = CampaignAnalysisSpec.data_view(_profile(), SyncJobStore(fake))

        # The window stays the SP campaign sync's; its last success is SB's, later.
        assert (view.data_from, view.data_through) == (date(2026, 7, 14), date(2026, 9, 16))
        assert view.last_success_at == datetime(2026, 9, 18, 2, 10, tzinfo=timezone.utc)

    def test_while_an_sb_or_sd_campaign_request_rewrites_days_the_planning_waits_too(self):
        fake = FakeRest([_rpc_campaign("1", "Alpha", 25.0, 0, 0.0)])
        _campaign_job(fake)
        _campaign_job(fake, status="running", job_id=443, kind="sd_campaigns")

        summary = _runner(fake, [_profile()]).plan()

        assert summary.analyses_queued == 0 and fake.campaign_reads == []


def test_the_search_term_runners_still_wait_on_the_search_term_sync():
    """The hook is optional: a spec without source_job_kind keeps the behavior every module had."""
    from core.ai_analysis.bid_analysis_job import BidAnalysisSpec
    from core.ai_analysis.str_analysis_job import StrAnalysisSpec

    assert not hasattr(StrAnalysisSpec, "source_job_kind") and not hasattr(BidAnalysisSpec, "source_job_kind")
    assert not hasattr(StrAnalysisSpec, "data_view") and not hasattr(BidAnalysisSpec, "data_view")


def test_the_migration_lets_the_database_accept_this_module_and_validate_its_window():
    migration = __import__("pathlib").Path("deploy/db/migrations/014_bulk_campaigns_ai.sql").read_text(encoding="utf-8")

    assert "select p_module in ('str', 'bid_optimizer', 'bulk_campaigns')" in migration
    assert "if p_module = 'bulk_campaigns' then" in migration and "job_kind = 'sp_campaigns'" in migration
    assert "grant execute on function campaigns_between(text, date, date) to web_user, ai_worker" in migration


def test_the_analysis_worker_may_read_the_sb_and_sd_campaigns_it_now_analyzes():
    migration = __import__("pathlib").Path("deploy/db/migrations/015_targeting_sb_sd.sql").read_text(encoding="utf-8")

    assert "grant select on ads_sb_sd_campaign, ads_sb_sd_campaign_daily to ai_worker;" in migration
    assert ("grant execute on function sb_legacy_history_done(text), product_campaigns_between(text, date, date) "
            "to ai_worker;") in migration

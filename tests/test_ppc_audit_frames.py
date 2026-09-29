"""PPC Audit Pro's two sources read into the same frames: a Bulk File by hand, and the synced Amazon Ads data.

The synced account lives in an in-memory PostgREST that the page and MCP tests reuse. No network.
"""
import csv
import io
import math
import zipfile
from datetime import date, datetime, timezone

import pandas as pd
import pytest
import requests

from core.amazon_ads.product_provider import SB_SEARCH_TERM_COLUMNS
from core.amazon_ads.report_provider import ProfileOption, ReportProvider
from core.amazon_ads.structure_provider import (
    AD_GROUP,
    BIDDING_ADJUSTMENT,
    CAMPAIGN,
    KEYWORD,
    PRODUCT_AD,
    PRODUCT_TARGETING,
    ROW_COLUMNS,
    SB_SD_TARGET_COLUMNS,
)
from core.ppc_audit.bulk_file import frames_from_bulk_file
from core.ppc_audit.checks import run_audit
from core.ppc_audit.frames import (
    SB_SEARCH_TERMS,
    SP_TARGET_METRICS,
    SP_TARGETS,
    product_campaign_sheet,
    search_term_sheet,
)
from core.ppc_audit.synced_reads import (
    AUDIT_ENTITIES,
    NOT_LISTED_REASON,
    SB_SEARCH_TERMS_NOT_SYNCED,
    STRUCTURE_PENDING_REASON,
    TARGETS_NOT_LISTED,
    read_synced_audit,
)
from tests.test_bulk_parser import _asegurar_fixture as synthetic_bulk_file

PROFILE_ID = "111"
START, END = date(2026, 9, 9), date(2026, 9, 22)
LISTED = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
SEARCH_TERM_COLUMNS = ["campaign_id", "ad_group_id", "keyword_type", "keyword_id", "match_type", "targeting",
                       "search_term", "campaign_name", "campaign_status", "ad_group_name", "keyword_text",
                       "ad_keyword_status", "portfolio_id", "portfolio_name", "currency_code", "impressions", "clicks",
                       "purchases_7d", "units_7d", "purchases_14d", "units_14d", "cost", "sales_7d", "sales_14d"]
PRODUCT_CAMPAIGN_COLUMNS = ["ad_product", "campaign_id", "name", "state", "start_date", "budget_type", "cost_type",
                            "portfolio_id", "portfolio_name", "is_multi_ad_groups", "bid_strategy", "metrics_known",
                            "currency_code", "budget_amount", "impressions", "clicks", "purchases",
                            "purchases_clicks", "viewable_impressions", "cost", "sales", "sales_clicks"]


def profile_row(**overrides) -> dict:
    row = {"profile_id": PROFILE_ID, "account_id": 1, "cliente": "Luna Kids", "account_name": "Luna Kids US",
           "country_code": "US", "currency_code": "USD", "account_type": "seller", "timezone": "America/New_York",
           "status": "active", "data_from": "2026-07-20", "data_through": END.isoformat(),
           "refreshed_on": "2026-09-23", "last_success_at": LISTED.isoformat(), "last_error": ""}
    row.update(overrides)
    return row


def structure_row(entity: str, **values) -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"entity": entity, "campaign_id": "1", "campaign_name": "Luna - SP - KW - EXACT", "state": "ENABLED",
                "metrics_known": "f", "currency_code": "USD", "listed_at": LISTED.isoformat()})
    row.update(values)
    return row


def _metrics(impressions, clicks, cost, orders, sales) -> dict:
    return {"metrics_known": "t", "impressions": impressions, "clicks": clicks, "cost": cost,
            "purchases_7d": orders, "sales_7d": sales, "purchases_14d": orders, "sales_14d": sales}


STRUCTURE = [
    structure_row(CAMPAIGN, entity_id="1", targeting_type="MANUAL", bidding_strategy="LEGACY_FOR_SALES",
                  budget_amount="20", budget_type="DAILY", **_metrics(1500, 40, 30.0, 3, 90.0)),
    structure_row(CAMPAIGN, campaign_id="2", entity_id="2", campaign_name="Luna - SP - AUTO", targeting_type="AUTO",
                  bidding_strategy="MANUAL", **_metrics(4000, 20, 15.0, 1, 25.0)),
    structure_row(BIDDING_ADJUSTMENT, placement="PLACEMENT_TOP", percentage="50"),
    structure_row(AD_GROUP, ad_group_id="10", entity_id="10", ad_group_name="Core", default_bid="0.60"),
    structure_row(KEYWORD, ad_group_id="10", entity_id="k1", ad_group_name="Core", target_kind="keyword",
                  target_text="luna pajamas", match_type="EXACT", own_bid="0.80", bid="0.80",
                  **_metrics(1500, 40, 30.0, 3, 90.0)),
    structure_row(KEYWORD, ad_group_id="10", entity_id="k2", ad_group_name="Core", target_kind="keyword",
                  target_text="kids sleep sack", match_type="EXACT", default_bid="0.60", bid="0.60",
                  **_metrics(0, 0, 0, 0, 0)),
    structure_row(PRODUCT_TARGETING, campaign_id="2", campaign_name="Luna - SP - AUTO", ad_group_id="20",
                  entity_id="t1", target_kind="auto", target_text="close-match", bid="0.40",
                  **_metrics(4000, 20, 15.0, 1, 25.0)),
    structure_row(PRODUCT_AD, ad_group_id="10", entity_id="a1", asin="B0LUNA0001", sku="LUNA-1"),
]


def _term(search_term, *, campaign_id="1", campaign_name="Luna - SP - KW - EXACT", keyword_type="EXACT",
          targeting=None, clicks=10, orders=0, cost=5.0, sales=0.0) -> dict:
    return {"campaign_id": campaign_id, "ad_group_id": "10", "keyword_type": keyword_type, "keyword_id": "k1",
            "match_type": keyword_type if keyword_type in ("EXACT", "PHRASE", "BROAD") else "",
            "targeting": targeting or search_term, "search_term": search_term, "campaign_name": campaign_name,
            "campaign_status": "ENABLED", "ad_group_name": "Core", "keyword_text": "luna pajamas",
            "ad_keyword_status": "ENABLED", "portfolio_id": "", "portfolio_name": "", "currency_code": "USD",
            "impressions": 400, "clicks": clicks, "purchases_7d": orders, "units_7d": orders,
            "purchases_14d": orders, "units_14d": orders, "cost": cost, "sales_7d": sales, "sales_14d": sales}


SEARCH_TERMS = [
    _term("luna pajamas", clicks=30, orders=3, cost=25.0, sales=90.0),
    _term("cheap pajamas", clicks=10, cost=5.0),
    _term("baby blanket", campaign_id="2", campaign_name="Luna - SP - AUTO", keyword_type="TARGETING_EXPRESSION_PREDEFINED",
          targeting="close-match", clicks=20, orders=1, cost=15.0, sales=25.0),
]


def _product_campaign(product, campaign_id, name, *, state="ENABLED", metrics_known="t", cost="10", sales="30",
                      multi="t") -> dict:
    row = dict.fromkeys(PRODUCT_CAMPAIGN_COLUMNS, "0")
    row.update({"ad_product": product, "campaign_id": campaign_id, "name": name, "state": state,
                "start_date": "2026-01-01", "budget_type": "DAILY", "cost_type": "CPC", "portfolio_id": "",
                "portfolio_name": "", "is_multi_ad_groups": multi, "bid_strategy": "MANUAL",
                "metrics_known": metrics_known, "currency_code": "USD", "budget_amount": "15", "impressions": "900",
                "clicks": "12", "purchases": "2", "purchases_clicks": "2", "cost": cost, "sales": sales,
                "sales_clicks": sales})
    return row


PRODUCT_CAMPAIGNS = [_product_campaign("SB", "5", "Luna - SB - Brand"),
                     _product_campaign("SD", "7", "Luna - SD - Remarketing views", cost="8", sales="0"),
                     _product_campaign("SB", "6", "Luna - SB - Old", state="ARCHIVED", cost="2", sales="0")]


def _sb_sd_target(product, campaign_id, text, *, kind="keyword", match="EXACT", cost="6", sales="0") -> dict:
    row = dict.fromkeys(SB_SD_TARGET_COLUMNS, "")
    row.update({"entity": "keyword" if kind == "keyword" else "product_targeting", "campaign_id": campaign_id,
                "ad_group_id": "50", "entity_id": f"{product}-{text}", "campaign_name": f"{product} campaign",
                "campaign_state": "ENABLED", "cost_type": "CPC", "ad_group_name": "AG", "state": "ENABLED",
                "target_kind": kind, "target_text": text, "match_type": match if kind == "keyword" else "",
                "bid": "1.0", "impressions": "300", "clicks": "4", "cost": cost, "purchases": "0", "sales": sales,
                "purchases_clicks": "0", "sales_clicks": sales, "metrics_known": "t", "currency_code": "USD",
                "listed_at": LISTED.isoformat()})
    return row


SB_TARGETS = [_sb_sd_target("SB", "5", "luna", cost="6", sales="40"), _sb_sd_target("SB", "5", "pajamas",
                                                                                     match="BROAD", cost="4")]
SD_TARGETS = [_sb_sd_target("SD", "7", 'views=(exactProduct lookback=30)', kind="audience", cost="8")]


def _sb_search_term(term, *, cost="3", sales="0") -> dict:
    row = dict.fromkeys(SB_SEARCH_TERM_COLUMNS, "0")
    row.update({"campaign_id": "5", "campaign_name": "Luna - SB - Brand", "ad_group_id": "50", "keyword_id": "kw5",
                "keyword_text": "luna", "match_type": "EXACT", "search_term": term, "impressions": "100",
                "clicks": "2", "cost": cost, "sales": sales, "sales_clicks": sales, "currency_code": "USD"})
    return row


SB_SEARCH_TERMS_ROWS = [_sb_search_term("luna brand", cost="5", sales="30"), _sb_search_term("luna cheap")]


def job_row(kind: str, *, window_end: date = END, warning: str = "") -> dict:
    return {"id": abs(hash(kind)) % 10_000, "integration_slug": "amazon_ads", "job_kind": kind,
            "trigger": "scheduled_daily", "external_account_id": PROFILE_ID, "status": "completed",
            "phase": "", "attempts": 0, "max_attempts": 6, "warning": warning,
            "window_start": "2026-07-20", "window_end": window_end.isoformat(), "local_day": "2026-09-23",
            "finished_at": LISTED.isoformat(), "created_at": LISTED.isoformat()}


SYNCED_JOBS = [job_row(kind) for kind in ("sp_search_terms", "campaign_entities", "sp_targets", "sp_campaigns",
                                          "sp_targeting", "sb_search_terms")]


def http_error(status: int, body: bytes) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response._content = body
    return requests.HTTPError(response=response)


class AuditRest:
    """An in-memory PostgREST with one synced account: its profile, its sync jobs and the reads PPC Audit makes."""

    MISSING = http_error(404, b'{"code":"PGRST202","message":"Could not find the function"}')

    def __init__(self, *, structure=STRUCTURE, jobs=SYNCED_JOBS, search_terms=SEARCH_TERMS,
                 product_campaigns=PRODUCT_CAMPAIGNS, sb_targets=SB_TARGETS, sd_targets=SD_TARGETS,
                 sb_search_terms=SB_SEARCH_TERMS_ROWS, missing=(), fail=False):
        self.structure, self.jobs, self.search_terms = list(structure), list(jobs), list(search_terms)
        self.product_campaigns, self.sb_targets, self.sd_targets = product_campaigns, sb_targets, sd_targets
        self.sb_search_terms, self.missing, self.fail = sb_search_terms, set(missing), fail
        self.reads: list[tuple[str, dict]] = []

    def select(self, table, params):
        if table == "ads_profile_sync":
            return [profile_row()]
        if table == "integration_sync_jobs":
            kind = str(params.get("job_kind", "")).removeprefix("eq.")
            return [dict(job) for job in self.jobs if job["job_kind"] == kind][:1]
        if table in ("ads_report_requests", "ai_analysis_settings", "ai_analyses"):
            return []
        raise AssertionError(f"unexpected select on {table}")

    def rpc_csv(self, name, args, *, timeout_s=8):
        self.reads.append((name, args))
        if self.fail:
            raise requests.ConnectionError("rest-gateway down")
        if name in self.missing:
            raise self.MISSING
        if name == "search_terms_between":
            return _csv(SEARCH_TERM_COLUMNS, self.search_terms)
        if name == "sp_structure_between":
            wanted = set(args.get("p_entities") or ())
            return _csv(ROW_COLUMNS, [row for row in self.structure if not wanted or row["entity"] in wanted])
        if name == "product_campaigns_between":
            return _csv(PRODUCT_CAMPAIGN_COLUMNS, self.product_campaigns)
        if name == "sb_sd_targets_between":
            rows = self.sb_targets if args["p_ad_product"] == "SB" else self.sd_targets
            return _csv(SB_SD_TARGET_COLUMNS, rows)
        if name == "sb_search_terms_between":
            return _csv(SB_SEARCH_TERM_COLUMNS, self.sb_search_terms)
        raise AssertionError(f"unexpected rpc {name}")


def _csv(columns, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def option() -> ProfileOption:
    return ProfileOption.from_row(profile_row())


def read(rest: AuditRest):
    source = ReportProvider(rest).search_terms(option(), START, END)
    return read_synced_audit(rest, option(), START, END, source.frame, attribution_days=source.attribution_days)


# ---------------------------------------------------------------- a Bulk File by hand

def test_the_synthetic_bulk_file_splits_into_entities_with_text_ids():
    frames = frames_from_bulk_file(synthetic_bulk_file().read_bytes())

    assert frames.from_file and frames.currency_code == ""
    assert (len(frames.sp_campaigns), len(frames.sp_keywords), len(frames.sp_product_ads)) == (6, 5, 2)
    assert frames.sp_search_terms["Campaign ID"].map(type).eq(str).all()
    assert not frames.sp_keywords["Campaign ID"].str.contains(r"\.|e\+", regex=True).any()
    assert frames.sp_search_terms["Spend"].dtype.kind == "f"
    assert frames.sb_campaigns.empty and frames.sd_targets.empty and frames.unavailable == {}


def _bulk_bytes(sheets: dict[str, list[dict]]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def test_sd_reads_its_targets_not_its_ad_groups_so_nothing_counts_twice():
    rows = [{"Entity": entity, "Campaign ID": 7, "Spend": spend, "Sales": 0}
            for entity, spend in (("Campaign", 20), ("Ad Group", 20), ("Audience Targeting", 12),
                                  ("Product Targeting", 8))]
    frames = frames_from_bulk_file(_bulk_bytes({"Sponsored Display Campaigns": rows}))

    assert list(frames.sd_targets["Entity"]) == ["Audience Targeting", "Product Targeting"]
    assert run_audit(frames).target_waste.sd.waste == 20


def test_the_bulk_ratios_lose_their_symbols_and_a_missing_metric_is_zero():
    rows = [{"Entity": "Campaign", "Campaign ID": 1, "Campaign Name": "A", "Spend": None, "Sales": 10,
             "ACOS": "25.5%", "CPC": "$1.20"}]
    campaigns = frames_from_bulk_file(_bulk_bytes({"Sponsored Products Campaigns": rows})).sp_campaigns

    assert campaigns.loc[0, ["Spend", "ACOS", "CPC"]].tolist() == [0, 25.5, 1.2]


def test_a_file_that_is_not_an_excel_workbook_raises_what_the_page_catches():
    with pytest.raises(ValueError):
        frames_from_bulk_file(b"not a workbook")
    with pytest.raises(zipfile.BadZipFile):
        frames_from_bulk_file(b"PK\x03\x04broken zip")


# ---------------------------------------------------------------- the synced data

def test_the_search_terms_read_as_the_bulk_search_term_sheet_with_the_accounts_attribution():
    frame = ReportProvider(AuditRest()).search_terms(option(), START, END).frame

    sheet = search_term_sheet(frame, 7).set_index("Customer Search Term")

    assert sheet.loc["luna pajamas", ["Campaign ID", "Keyword Text", "Match Type", "Product Targeting Expression",
                                      "Spend", "Sales", "Orders"]].tolist() == \
        ["1", "luna pajamas", "Exact", "", 25.0, 90.0, 3]
    assert sheet.loc["baby blanket", ["Keyword Text", "Product Targeting Expression"]].tolist() == \
        ["", "close-match"]


def test_sb_and_sd_campaigns_split_by_ad_product_and_keep_unknown_metrics_unknown():
    campaigns = pd.DataFrame({"Campaign name": ["B", "D", "Old"], "Campaign ID": ["5", "7", "8"],
                              "State": ["ENABLED", "PAUSED", "ENABLED"],
                              "Type": ["Sponsored Brands", "Sponsored Display", "Sponsored Brands"],
                              "Campaign bid strategy": ["Fixed bids", "", ""],
                              "Impressions": pd.array([10, 20, pd.NA], dtype="Int64"),
                              "Clicks": pd.array([1, 2, pd.NA], dtype="Int64"), "Total cost": [3.0, 4.0, math.nan],
                              "Sales": [9.0, 0.0, math.nan], "Purchases": pd.array([1, 0, pd.NA], dtype="Int64")})

    sb = product_campaign_sheet(campaigns, "Sponsored Brands")

    assert list(sb["Campaign ID"]) == ["5", "8"] and list(sb["State"]) == ["enabled", "enabled"]
    assert sb.loc[0, ["Spend", "Sales", "Orders"]].tolist() == [3.0, 9.0, 1.0]
    assert math.isnan(sb.loc[1, "Spend"])
    assert list(product_campaign_sheet(campaigns, "Sponsored Display")["Campaign ID"]) == ["7"]


def test_a_synced_account_reads_its_whole_structure_with_its_quiet_keywords():
    rest = AuditRest()

    synced = read(rest)

    frames = synced.frames
    assert not frames.from_file and frames.currency_code == "USD" and frames.unavailable == {}
    assert list(frames.sp_keywords["Keyword Text"]) == ["kids sleep sack", "luna pajamas"]
    assert list(frames.sp_product_targets["Product Targeting Expression"]) == ["close-match"]
    assert list(frames.sp_placements["Placement"]) == ["PLACEMENT_TOP"]
    assert list(frames.sb_campaigns["Campaign ID"]) == ["5", "6"]
    assert list(frames.sb_keywords["Match Type"]) == ["Exact", "Broad"]
    assert list(frames.sb_search_terms["Customer Search Term"]) == ["luna brand", "luna cheap"]
    assert (synced.listed_at, synced.campaigns_through, synced.targeting_through) == (LISTED, END, END)
    structure_reads = [args for name, args in rest.reads if name == "sp_structure_between"]
    assert structure_reads == [{"p_profile_id": PROFILE_ID, "p_from": "2026-09-09", "p_to": "2026-09-22",
                                "p_entities": list(AUDIT_ENTITIES)}]
    graduation = run_audit(frames).graduation
    assert list(graduation["Keyword Text"]) == ["kids sleep sack"] and list(graduation["Bid"]) == [0.6]


def test_without_migration_018_there_is_no_structure_to_audit():
    synced = read(AuditRest(missing={"sp_structure_between"}))

    assert synced.frames is None and synced.missing_reason == STRUCTURE_PENDING_REASON


def test_campaigns_never_listed_leave_nothing_to_audit():
    synced = read(AuditRest(structure=[], jobs=[job_row("sp_search_terms")]))

    assert synced.frames is None and synced.missing_reason == NOT_LISTED_REASON and not synced.refused


def test_a_campaign_listing_amazon_refused_says_so():
    refused = job_row("campaign_entities", warning="sin permiso para leer las campañas")

    synced = read(AuditRest(structure=[], jobs=[refused]))

    assert synced.refused and "sin permiso para leer las campañas" in synced.missing_reason


def test_keywords_never_listed_are_a_missing_part_not_zero_targets():
    campaigns_only = [row for row in STRUCTURE if row["entity"] == CAMPAIGN]
    jobs = [job for job in SYNCED_JOBS if job["job_kind"] != "sp_targets"]

    frames = read(AuditRest(structure=campaigns_only, jobs=jobs)).frames

    assert frames.unavailable[SP_TARGETS] == TARGETS_NOT_LISTED
    assert run_audit(frames).target_waste.sp is None


def test_targets_listed_without_any_metric_of_the_period_are_a_missing_part():
    unmeasured = [dict(row, metrics_known="f") if row["entity"] in (KEYWORD, PRODUCT_TARGETING) else row
                  for row in STRUCTURE]

    frames = read(AuditRest(structure=unmeasured)).frames

    assert "keywords y targets de Sponsored Products" in frames.unavailable[SP_TARGET_METRICS]
    assert run_audit(frames).graduation.empty


def test_sb_search_terms_not_synced_yet_are_a_missing_part():
    jobs = [job for job in SYNCED_JOBS if job["job_kind"] != "sb_search_terms"]

    frames = read(AuditRest(jobs=jobs)).frames

    assert frames.unavailable[SB_SEARCH_TERMS] == SB_SEARCH_TERMS_NOT_SYNCED
    assert run_audit(frames).search_term_waste.sb is None


def test_an_account_without_sb_does_not_ask_for_its_search_terms():
    rest = AuditRest(product_campaigns=[_product_campaign("SD", "7", "Luna - SD")], sb_targets=[])

    frames = read(rest).frames

    assert SB_SEARCH_TERMS not in frames.unavailable
    assert "sb_search_terms_between" not in [name for name, _ in rest.reads]


def test_metrics_behind_the_window_show_their_last_day():
    jobs = [job_row(kind, window_end=date(2026, 9, 20)) if kind == "sp_targeting" else job
            for kind, job in ((job["job_kind"], job) for job in SYNCED_JOBS)]

    synced = read(AuditRest(jobs=jobs))

    assert (synced.campaigns_through, synced.targeting_through) == (END, date(2026, 9, 20))


def test_a_base_that_cannot_be_read_raises_a_read_error():
    from core.amazon_ads.report_provider import ReportReadError

    with pytest.raises(ReportReadError):
        read_synced_audit(AuditRest(fail=True), option(), START, END, pd.DataFrame(), attribution_days=7)

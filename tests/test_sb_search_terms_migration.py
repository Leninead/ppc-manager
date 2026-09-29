"""021_sb_search_terms.sql: the SB search term days the worker writes and the read PPC Audit uses.

The suite has no Postgres, so these read the SQL text: the contract the sync and the provider rely on.
"""
import ast
import re
from datetime import date
from pathlib import Path

from core.amazon_ads import report_kinds
from core.amazon_ads.product_provider import SB_SEARCH_TERM_COLUMNS, SB_SEARCH_TERMS_RPC
from core.amazon_ads.product_rows import SB_LEGACY_SEARCH_TERM_ROWS, SB_SEARCH_TERM_ROWS
from core.amazon_ads.sync_planner import SB_LEGACY_KIND, SB_LEGACY_SEARCH_TERMS_KIND
from tests.test_sp_structure_migration import _body, _flat, _function, _returns_columns, _table

MIGRATION = Path("deploy/db/migrations/021_sb_search_terms.sql").read_text(encoding="utf-8")
TARGETING_MIGRATION = Path("deploy/db/migrations/015_targeting_sb_sd.sql").read_text(encoding="utf-8")
SMOKE = Path("deploy/db/smoke_readonly.py").read_text(encoding="utf-8")

READ_TYPES = {"impressions": "bigint", "clicks": "bigint", "cost": "numeric", "purchases": "bigint",
              "sales": "numeric", "purchases_clicks": "bigint", "sales_clicks": "numeric"}
# 015's filter: from v2 only the SB campaigns listed with the old format enter the day.
V2_FILTER = ("where p_source = 'v3' or exists ( select 1 from ads_sb_sd_campaign listed "
             "where listed.profile_id = p_profile_id and listed.ad_product = 'SB' "
             "and listed.campaign_id = row_data.campaign_id and listed.is_multi_ad_groups = false);")


def _table_columns() -> set[str]:
    lines = _table(MIGRATION, "ads_sb_search_term_daily").splitlines()[1:]
    return {line.split()[0] for line in lines
            if line.strip() and not line.strip().startswith(("--", "primary key"))}


def _parsed_row(parser, api_row: dict, day: date) -> dict:
    return parser.rows_by_day([api_row], profile_id="555", currency_code="USD", window_start=day,
                              window_end=day)[day][0]


def test_the_table_keeps_the_two_sources_apart_in_its_key():
    table = _flat(_table(MIGRATION, "ads_sb_search_term_daily"))

    assert "primary key (profile_id, report_date, source, campaign_id, ad_group_id, keyword_id, search_term)" in table
    assert "source text not null default 'v3' collate \"C\" check (source in ('v3', 'v2'))" in table
    assert "search_term text not null collate \"C\"" in table


def test_the_table_has_exactly_the_columns_both_parsers_write_plus_the_source_and_the_load_time():
    day = date(2026, 9, 8)
    v3_row = _parsed_row(SB_SEARCH_TERM_ROWS, {"date": "2026-09-08", "campaignId": 1, "searchTerm": "demo"}, day)
    v2_row = _parsed_row(SB_LEGACY_SEARCH_TERM_ROWS, {"campaignId": 1, "query": "demo"}, day)

    assert set(v3_row) == set(v2_row)
    # jsonb_populate_recordset lands a key the table lacks nowhere, and one the rows lack as NULL.
    assert _table_columns() == set(v3_row) | {"source", "ingested_at"}


def test_the_day_replace_takes_what_the_worker_sends():
    statement = _flat(_function(MIGRATION, "replace_sb_search_term_day"))
    called = {"p_profile_id", "p_day", "p_rows"}

    assert statement.startswith("create or replace function replace_sb_search_term_day(p_profile_id text, "
                                "p_day date, p_rows jsonb, p_source text default 'v3') returns integer")
    for kind in (report_kinds.SB_SEARCH_TERMS, report_kinds.SB_LEGACY_SEARCH_TERMS):
        assert kind.replace_day_rpc == "replace_sb_search_term_day"
        assert called | set(kind.rpc_args) <= {"p_profile_id", "p_day", "p_rows", "p_source"}


def test_a_source_rewrites_only_its_own_rows_of_the_day():
    body = _flat(_body(_function(MIGRATION, "replace_sb_search_term_day")))

    assert ("delete from ads_sb_search_term_daily where profile_id = p_profile_id and report_date = p_day "
            "and source = p_source;") in body
    assert ("if exists (select 1 from ads_sb_search_term_daily where profile_id = p_profile_id "
            "and report_date = p_day and source = p_source) then return -1;") in body
    assert "if p_rows is null or jsonb_typeof(p_rows) <> 'array' then raise exception" in body
    assert "if p_source not in ('v3', 'v2') then raise exception" in body
    assert "insert into ads_sb_search_term_daily ( profile_id, report_date, source," in body
    assert "select p_profile_id, p_day, p_source, row_data.campaign_id," in body


def test_v2_keeps_only_the_campaigns_of_the_old_format_as_the_sb_campaign_days_do():
    assert V2_FILTER in _flat(_body(_function(TARGETING_MIGRATION, "replace_sb_sd_campaign_day")))
    assert V2_FILTER in _flat(_body(_function(MIGRATION, "replace_sb_search_term_day")))


def test_the_read_returns_the_columns_the_provider_reads():
    statement = _function(MIGRATION, SB_SEARCH_TERMS_RPC)

    assert _flat(statement).startswith(
        f"create or replace function {SB_SEARCH_TERMS_RPC}(p_profile_id text, p_from date, p_to date) returns table (")
    assert [name for name, _ in _returns_columns(statement)] == list(SB_SEARCH_TERM_COLUMNS)
    assert {name: kind for name, kind in _returns_columns(statement)} == {
        name: READ_TYPES.get(name, "text") for name in SB_SEARCH_TERM_COLUMNS}
    assert "language sql\nstable\nas $$" in statement


def test_the_read_sums_each_term_of_each_keyword_over_the_range_and_leaves_the_order_to_its_reader():
    body = _flat(_body(_function(MIGRATION, SB_SEARCH_TERMS_RPC)))

    assert "where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to" in body
    assert "group by daily.campaign_id, daily.ad_group_id, daily.keyword_id, daily.search_term" in body
    for metric in READ_TYPES:
        assert f"sum(daily.{metric})" in body, metric
    assert "order by" not in body


def test_v2_rows_count_once_their_history_loaded_as_in_the_sb_campaign_reads():
    body = _flat(_body(_function(MIGRATION, SB_SEARCH_TERMS_RPC)))
    campaign_history = _flat(_body(_function(TARGETING_MIGRATION, "sb_legacy_history_done")))
    campaign_check = campaign_history[campaign_history.index("select exists ("):campaign_history.index(" );") + 2]

    assert "cross join legacy" in body and "and (daily.source = 'v3' or legacy.done)" in body
    # The same check as sb_legacy_history_done, on the search terms' own v2 history.
    assert f"'{SB_LEGACY_KIND}'" in campaign_check
    assert campaign_check.replace(f"'{SB_LEGACY_KIND}'", f"'{SB_LEGACY_SEARCH_TERMS_KIND}'") in body


def test_the_read_names_the_campaign_and_takes_v2s_keyword_from_the_sb_lists():
    body = _flat(_body(_function(MIGRATION, SB_SEARCH_TERMS_RPC)))

    assert ("left join ads_sb_sd_campaign campaign on campaign.profile_id = p_profile_id "
            "and campaign.ad_product = 'SB' and campaign.campaign_id = totals.campaign_id") in body
    assert ("left join ads_target keyword on keyword.profile_id = p_profile_id and keyword.ad_product = 'SB' "
            "and keyword.target_id = totals.keyword_id;") in body
    assert "coalesce(campaign.name, '')" in body
    assert "coalesce(nullif(totals.keyword_text, ''), keyword.target_text, '')" in body
    assert "coalesce(nullif(totals.match_type, ''), keyword.match_type, '')" in body
    # Archived campaigns and keywords stay in their lists with an older seen_at, and old days still need their names.
    assert "seen_at" not in body


def test_the_grants_revoke_the_defaults_first_let_the_app_read_and_the_worker_write():
    flat = _flat(MIGRATION)
    first_grant = MIGRATION.index("\ngrant ")

    assert MIGRATION.index("revoke all on ads_sb_search_term_daily from web_user;") < first_grant
    assert ("revoke all on function replace_sb_search_term_day(text, date, jsonb, text), "
            "sb_search_terms_between(text, date, date) from public, web_user;") in flat
    assert MIGRATION.index("\nrevoke all on function") < first_grant
    assert "grant select on ads_sb_search_term_daily to web_user;" in flat
    assert "grant execute on function sb_search_terms_between(text, date, date) to web_user;" in flat
    assert "grant select, insert, update, delete on ads_sb_search_term_daily to integ_worker;" in flat
    assert "grant execute on function replace_sb_search_term_day(text, date, jsonb, text) to integ_worker;" in flat
    assert len(re.findall(r"\ngrant ", MIGRATION)) == 4
    assert "ai_worker" not in MIGRATION and "security definer" not in MIGRATION


def test_the_migration_is_additive_and_reloads_the_postgrest_schema():
    assert "drop " not in MIGRATION.lower()
    assert MIGRATION.index("begin;") < MIGRATION.index("commit;")
    assert MIGRATION.rstrip().endswith("notify pgrst, 'reload schema';")


def test_the_read_only_smoke_probes_the_new_table():
    tables = next(ast.literal_eval(node.value) for node in ast.walk(ast.parse(SMOKE))
                  if isinstance(node, ast.Assign) and [target.id for target in node.targets] == ["TABLES"])

    assert ("ads_sb_search_term_daily", "profile_id") in tables

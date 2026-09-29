"""023_seller_reports.sql: the Seller Central tables and the one write path the app and the SP-API worker share.

The suite has no Postgres, so these read the SQL text: the contract core/seller_reports and the next tickets rely on.
The behaviour itself was run against Postgres 16 and PostgREST through deploy/db/e2e_selfhosted_db.py.
"""
import ast
import re
from pathlib import Path

from core.seller_reports import columns, store
from tests.test_sp_structure_migration import _body, _flat, _function, _table

MIGRATION = Path("deploy/db/migrations/023_seller_reports.sql").read_text(encoding="utf-8")
SMOKE = Path("deploy/db/smoke_readonly.py").read_text(encoding="utf-8")

TABLES = ("seller_accounts", "seller_report_loads", "seller_report_periods", "seller_report_period_history",
          "seller_sales_traffic_daily", "seller_sales_traffic_by_asin", "seller_search_query_performance")
DATASETS = (columns.SALES_TRAFFIC_DAILY, columns.SALES_TRAFFIC_BY_ASIN, columns.SQP_BRAND_VIEW,
            columns.SQP_ASIN_VIEW)
DATA_TABLES = {
    "seller_sales_traffic_daily": (columns.SALES_TRAFFIC_DAILY_COLUMNS, {"seller_account_id"}, "day"),
    "seller_sales_traffic_by_asin": (columns.SALES_TRAFFIC_BY_ASIN_COLUMNS,
                                     {"seller_account_id", "range_start", "range_end"}, "child_asin"),
    "seller_search_query_performance": (columns.SEARCH_QUERY_PERFORMANCE_COLUMNS,
                                        {"seller_account_id", "view", "brand_or_asin", "period_type", "period_start",
                                         "period_end"}, "search_query"),
}
APP_FUNCTIONS = {"upload_seller_sales_traffic_daily", "upload_seller_sales_traffic_by_asin",
                 "upload_seller_search_query_performance", "delete_seller_report_periods",
                 "revert_seller_report_load", "set_selling_partner_id", "delete_seller_account",
                 "seller_account_for_ads_profile"}
WORKER_FUNCTIONS = {"save_seller_sales_traffic_daily", "save_seller_sales_traffic_by_asin",
                    "save_seller_search_query_performance", "seller_account_for_ads_profile"}
COLUMN_LINE = re.compile(r"^ {4}([a-z_0-9]+) +(text|integer|bigint|date|numeric\(\d+,\d+\)|timestamptz|jsonb|serial"
                         r"|bigserial)(?=[\s,]|$)(.*)$")


def _columns(table: str) -> dict[str, str]:
    """Each column of the table and the rest of its line (collation, null-ness, default, check)."""
    return {match.group(1): match.group(3) for line in _table(MIGRATION, table).splitlines()
            if (match := COLUMN_LINE.match(line))}


def _functions() -> set[str]:
    return set(re.findall(r"^create or replace function (\w+)\(", MIGRATION, re.MULTILINE))


def _granted(role: str) -> set[str]:
    names: set[str] = set()
    for statement in re.findall(r"^grant execute on function (.+?);", MIGRATION, re.MULTILINE | re.DOTALL):
        functions, grantees = statement.rsplit(" to ", 1)
        if role in {grantee.strip() for grantee in grantees.split(",")}:
            names |= set(re.findall(r"(\w+)\(", functions))
    return names


def test_each_data_table_holds_the_python_columns_plus_the_period_arguments():
    for table, (row_columns, argument_columns, _) in DATA_TABLES.items():
        assert len(set(row_columns)) == len(row_columns), table
        assert set(_columns(table)) == set(row_columns) | argument_columns, table


def test_the_function_that_strips_the_arguments_names_the_same_columns():
    body = _flat(_body(_function(MIGRATION, "seller_report_argument_columns")))

    for dataset, table in ((columns.SALES_TRAFFIC_DAILY, "seller_sales_traffic_daily"),
                           (columns.SALES_TRAFFIC_BY_ASIN, "seller_sales_traffic_by_asin"),
                           (columns.SQP_BRAND_VIEW, "seller_search_query_performance"),
                           (columns.SQP_ASIN_VIEW, "seller_search_query_performance")):
        listed = re.search(rf"when '{dataset}' then array\[([^\]]*)\]", body).group(1)
        assert set(re.findall(r"'(\w+)'", listed)) == DATA_TABLES[table][1], dataset


def test_a_metric_the_export_did_not_bring_stays_null_rather_than_zero():
    for table, (row_columns, _, row_key) in DATA_TABLES.items():
        table_columns = _columns(table)
        for column in row_columns:
            if column == row_key:
                assert "not null" in table_columns[column], (table, column)
            else:
                assert "not null" not in table_columns[column] and "default" not in table_columns[column], (
                    table, column)


def test_the_python_datasets_are_the_ones_the_tables_accept():
    for table in ("seller_report_loads", "seller_report_periods"):
        accepted = re.search(r"check \(dataset in \(([^)]*)\)\)", _flat(_table(MIGRATION, table))).group(1)
        assert tuple(re.findall(r"'(\w+)'", accepted)) == DATASETS, table
    assert "when 'brand' then 'sqp_brand_view' when 'asin' then 'sqp_asin_view'" in _flat(MIGRATION)
    assert (columns.BRAND_VIEW, columns.ASIN_VIEW) == ("brand", "asin")


def test_the_python_statuses_and_sources_are_the_ones_the_functions_return():
    def literals(function: str) -> set[str]:
        return set(re.findall(r"'(\w+)'", _body(_function(MIGRATION, function))))

    assert literals("seller_report_save_status") == {store.INSERTED, store.UNCHANGED, store.CONFLICT,
                                                     store.REPLACED}
    assert {store.DELETED, store.CONFLICT} <= literals("delete_seller_report_periods")
    assert {store.RESTORED, store.REMOVED, store.SKIPPED} <= literals("revert_seller_report_load")
    sources = re.search(r"check \(source in \(([^)]*)\)\)", _flat(_table(MIGRATION, "seller_report_loads"))).group(1)
    assert set(re.findall(r"'(\w+)'", sources)) == {store.MANUAL, store.SP_API}


def test_a_seller_account_is_the_ads_account_of_one_marketplace_and_its_seller_id_waits_to_be_verified():
    table = _flat(_table(MIGRATION, "seller_accounts"))

    assert "ads_entity_id text not null collate \"C\"" in table
    assert "marketplace_id text not null collate \"C\"" in table
    assert "selling_partner_id text collate \"C\"," in table
    assert "unique (ads_entity_id, marketplace_id)" in table
    assert "unique (selling_partner_id, marketplace_id)" in table
    assert "check ((selling_partner_id is null) = (selling_partner_id_source = ''))" in table


def test_every_function_loses_the_default_execute_before_any_grant():
    flat = _flat(MIGRATION)
    first_grant = MIGRATION.index("\ngrant ")
    revoked = flat[flat.index("revoke all on function "):]
    revoked = revoked[:revoked.index(" from public, web_user;")]

    assert set(re.findall(r"(\w+)\(", revoked)) == _functions()
    assert MIGRATION.index("\nrevoke all on function ") < first_grant
    assert ("revoke all on " + ", ".join(TABLES) + " from web_user;") in flat
    assert "revoke all on sequence seller_accounts_id_seq, seller_report_loads_id_seq from web_user;" in flat
    assert MIGRATION.index("\nrevoke all on seller_accounts") < first_grant


def test_nobody_writes_the_tables_directly_and_both_roles_read_them():
    flat = _flat(MIGRATION)

    assert not re.search(r"\bgrant [^;]*\b(insert|update|delete|all)\b[^;]* on ", flat)
    assert ("grant select on " + ", ".join(TABLES) + " to web_user, integ_worker;") in flat


def test_the_app_and_the_worker_each_get_only_their_entry_points():
    assert _granted("web_user") == APP_FUNCTIONS
    assert _granted("integ_worker") == WORKER_FUNCTIONS
    assert _granted("ai_worker") == _granted("integ_provider") == set()


def test_every_granted_function_runs_as_its_owner_with_a_fixed_search_path_and_the_helpers_do_not():
    for name in _functions():
        header = _function(MIGRATION, name)
        header = header[:header.index("as $$")]
        granted = name in APP_FUNCTIONS | WORKER_FUNCTIONS
        assert ("security definer" in header) is granted, name
        assert ("set search_path = public, pg_temp" in header) is granted, name


def test_the_app_uploads_are_the_worker_writes_with_the_source_pinned_to_manual():
    for dataset in ("sales_traffic_daily", "sales_traffic_by_asin", "search_query_performance"):
        body = _flat(_body(_function(MIGRATION, f"upload_seller_{dataset}")))
        assert f"select * from save_seller_{dataset}(" in body
        assert "'manual'" in body and "p_source" not in body


def test_every_write_locks_the_account_and_ends_in_the_one_save():
    for dataset in ("sales_traffic_daily", "sales_traffic_by_asin", "search_query_performance"):
        body = _flat(_body(_function(MIGRATION, f"save_seller_{dataset}")))
        assert "perform seller_report_check_source(p_source);" in body
        assert body.index("perform seller_report_lock_account(p_account_id);") < body.index(
            "select * from seller_report_save(")
    for name in ("delete_seller_report_periods", "revert_seller_report_load", "set_selling_partner_id",
                 "delete_seller_account"):
        assert "seller_report_lock_account(" in _body(_function(MIGRATION, name)), name


def test_the_same_content_never_asks_and_only_the_hand_over_sp_api_does():
    rule = _flat(_body(_function(MIGRATION, "seller_report_save_status")))
    confirmation = _flat(_body(_function(MIGRATION, "seller_report_needs_confirmation")))

    assert rule.index("then 'unchanged'") < rule.index("then 'conflict'")
    assert ("select coalesce(p_existing_source, '') = 'sp_api' and p_source = 'manual' "
            "and not coalesce(p_replace_api_data, false);") in confirmation


def test_a_preview_or_one_conflict_writes_nothing_and_a_write_keeps_the_version_it_replaces():
    body = _flat(_body(_function(MIGRATION, "seller_report_save")))
    held_back = body.index("if p_preview or exists (select 1 from unnest(planned) planned_change "
                           "where planned_change.status = 'conflict')")

    assert held_back < body.index("new_load_id := seller_report_open_load(")
    assert body.index("perform seller_report_keep_version(") < body.index("perform seller_report_write_period(")
    delete = _flat(_body(_function(MIGRATION, "delete_seller_report_periods")))
    assert delete.index("perform seller_report_keep_version(") < delete.index("perform seller_report_write_period(")


def test_an_undo_only_touches_the_periods_the_load_still_owns():
    body = _flat(_body(_function(MIGRATION, "revert_seller_report_load")))

    assert "when 'save' then previous_version.existing_load_id is not distinct from p_load_id" in body
    assert "else previous_version.existing_load_id is null" in body
    assert "if load_to_revert.reverted_at is not null then return;" in body
    assert "where history.changed_by_load_id = p_load_id" in body


def test_the_migration_is_additive_and_reloads_the_postgrest_schema():
    assert "drop " not in MIGRATION.lower()
    assert MIGRATION.index("begin;") < MIGRATION.index("commit;")
    assert MIGRATION.rstrip().endswith("notify pgrst, 'reload schema';")


def test_the_read_only_smoke_probes_every_new_table():
    tables = next(ast.literal_eval(node.value) for node in ast.walk(ast.parse(SMOKE))
                  if isinstance(node, ast.Assign) and [target.id for target in node.targets] == ["TABLES"])

    assert {table for table, _ in tables} >= set(TABLES)

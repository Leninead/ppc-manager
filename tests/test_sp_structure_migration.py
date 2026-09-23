"""018_sp_structure.sql: the SP structure the listings keep, the effective bid and the read the app and the chat use.

The suite has no Postgres, so these read the SQL text: the contract the sync, the provider and the MCP rely on.
"""
import ast
import re
from pathlib import Path

import pytest

MIGRATION = Path("deploy/db/migrations/018_sp_structure.sql").read_text(encoding="utf-8")
TARGETING_MIGRATION = Path("deploy/db/migrations/015_targeting_sb_sd.sql").read_text(encoding="utf-8")
SMOKE = Path("deploy/db/smoke_readonly.py").read_text(encoding="utf-8")

PLACEMENT_COLUMNS = ("placement_top_pct", "placement_product_page_pct", "placement_rest_of_search_pct",
                     "amazon_business_pct")
TARGET_BID_COLUMNS = ["profile_id", "ad_product", "target_id", "campaign_id", "ad_group_id", "target_kind",
                      "target_text", "match_type", "state", "seen_at", "own_bid", "ad_group_name", "ad_group_state",
                      "default_bid", "bid"]
STRUCTURE_COLUMNS = [
    ("entity", "text"), ("campaign_id", "text"), ("ad_group_id", "text"), ("entity_id", "text"),
    ("campaign_name", "text"), ("ad_group_name", "text"), ("portfolio_id", "text"), ("portfolio_name", "text"),
    ("state", "text"), ("targeting_type", "text"), ("budget_amount", "numeric"), ("budget_type", "text"),
    ("bidding_strategy", "text"), ("placement", "text"), ("percentage", "integer"), ("asin", "text"),
    ("sku", "text"), ("target_kind", "text"), ("target_text", "text"), ("match_type", "text"),
    ("default_bid", "numeric"), ("own_bid", "numeric"), ("bid", "numeric"), ("impressions", "bigint"),
    ("clicks", "bigint"), ("cost", "numeric"), ("purchases_7d", "bigint"), ("sales_7d", "numeric"),
    ("purchases_14d", "bigint"), ("sales_14d", "numeric"), ("metrics_known", "boolean"),
    ("currency_code", "text"), ("listed_at", "timestamptz"),
]
ENTITY_ORDER = ("campaign", "bidding_adjustment", "ad_group", "keyword", "product_targeting", "product_ad",
                "negative_keyword", "campaign_negative_keyword", "negative_product_targeting",
                "campaign_negative_product_targeting")
UNION_BRANCHES = ("campaign_rows", "bidding_adjustment_rows", "ad_group_rows", "target_rows", "product_ad_rows",
                  "negative_rows")
PROGRESS_KEYS = ('"listing"', '"next_token"', '"seen_at"', '"rows"', '"pages"')


def _flat(text: str) -> str:
    return " ".join(text.split())


def _table(sql: str, name: str) -> str:
    start = sql.index(f"create table if not exists {name} (")
    return sql[start:sql.index("\n);", start)]


def _function(sql: str, name: str) -> str:
    start = sql.index(f"create or replace function {name}(")
    return sql[start:sql.index("$$;", start) + len("$$;")]


def _view(sql: str, name: str) -> str:
    start = sql.index(f"create or replace view {name} ")
    return sql[start:sql.index(";\n", start) + 1]


def _returns_block(statement: str) -> str:
    start = statement.index("returns table (")
    return statement[start:statement.index("\n)\n", start) + len("\n)")]


def _returns_columns(statement: str) -> list[tuple[str, str]]:
    return [tuple(line.strip().rstrip(",").split()) for line in _returns_block(statement).splitlines()[1:-1]]


def _body(statement: str) -> str:
    return statement[statement.index("as $$"):]


def _top_level(text: str, start: int = 0):
    """Yield (index, char) outside quotes and line comments, with the parenthesis depth at that char."""
    depth, index, quoted = 0, start, False
    while index < len(text):
        char = text[index]
        if quoted:
            quoted = char != "'"
        elif char == "'":
            quoted = True
        elif text.startswith("--", index):
            index = text.index("\n", index)
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        yield index, char, depth
        index += 1


def _cte(body: str, name: str) -> str:
    opening = body.index(f"    {name} as (") + len(f"    {name} as ")
    closing = next(index for index, char, depth in _top_level(body, opening) if char == ")" and depth == 0)
    return body[opening + 1:closing]


def _select_list(cte: str) -> list[str]:
    select_list = cte[cte.index("select ") + len("select "):cte.index("\n          from ")]
    items, start = [], 0
    for index, char, depth in _top_level(select_list):
        if char == "," and depth == 0:
            items.append(select_list[start:index])
            start = index + 1
    return [" ".join(item.split()) for item in items + [select_list[start:]]]


def _output_name(item: str) -> str:
    return item.split()[-1].split(".")[-1]


def test_the_ad_group_table_keeps_the_product_in_its_key_and_a_default_bid_that_can_be_unknown():
    table = _table(MIGRATION, "ads_ad_group")

    assert "primary key (profile_id, ad_product, ad_group_id)" in table
    assert "ad_product  text not null collate \"C\" check (ad_product in ('SP', 'SB', 'SD'))" in table
    assert "default_bid numeric(14,4),\n" in table
    assert "seen_at     timestamptz not null default now()" in table


def test_the_negatives_table_keys_each_of_the_four_listings_apart_and_reads_by_campaign():
    table = _table(MIGRATION, "ads_negative")

    assert "primary key (profile_id, ad_product, level, negative_kind, negative_id)" in table
    assert "check (level in ('campaign', 'ad_group'))" in table
    assert "check (negative_kind in ('keyword', 'product'))" in table
    assert "ad_group_id   text not null default ''" in table
    assert ("create index if not exists ads_negative_campaign_idx on ads_negative (profile_id, ad_product, "
            "campaign_id);") in MIGRATION


def test_the_sync_job_keeps_where_a_listing_done_in_parts_stopped_and_explains_its_shape():
    comment = MIGRATION[MIGRATION.index("comment on column integration_sync_jobs.progress is"):]
    comment = comment[:comment.index("';") + 2]

    assert "alter table integration_sync_jobs add column if not exists progress jsonb;" in MIGRATION
    for key in PROGRESS_KEYS:
        assert key in comment
    assert "NULL" in comment and "429" in comment


def test_the_listing_snapshot_keeps_the_last_complete_run_of_each_listing_per_profile():
    table = _table(MIGRATION, "ads_listing_snapshot")

    assert "primary key (profile_id, listing)" in table
    assert "profile_id   text not null collate \"C\"" in table
    assert "listing      text not null collate \"C\"" in table
    assert "seen_at      timestamptz not null,\n" in table
    assert "rows         integer not null,\n" in table
    assert "completed_at timestamptz not null default now()" in table


@pytest.mark.parametrize("column", PLACEMENT_COLUMNS)
def test_each_placement_adjustment_is_a_nullable_campaign_column_that_explains_zero_and_null(column):
    alter = _flat(MIGRATION[MIGRATION.index("alter table ads_campaign"):MIGRATION.index(";", MIGRATION.index(
        "alter table ads_campaign"))])
    comment = MIGRATION[MIGRATION.index(f"comment on column ads_campaign.{column} is"):]
    comment = comment[:comment.index("';") + 2]

    assert f"add column if not exists {column} integer" in alter
    assert "0: sin ajuste" in comment and "NULL: desconocido" in comment


def test_graduation_keeps_the_exact_result_columns_of_015_so_old_images_and_grants_keep_working():
    new = _function(MIGRATION, "graduation_targets_between")
    old = _function(TARGETING_MIGRATION, "graduation_targets_between")

    assert _returns_block(new) == _returns_block(old)
    assert new.startswith("create or replace function graduation_targets_between(p_profile_id text, p_from date, "
                          "p_to date)")


def test_the_effective_bid_rule_lives_once_in_the_target_bid_view():
    view = _view(MIGRATION, "ads_target_bid")
    select_list = view[view.index("select ") + len("select "):view.index("\n  from ads_target target")]
    items, start = [], 0
    for index, char, depth in _top_level(select_list):
        if char == "," and depth == 0:
            items.append(select_list[start:index])
            start = index + 1
    bid_coalesces = [segment for segment in MIGRATION.split("coalesce(")[1:]
                     if "bid" in segment[:segment.index(")")]]

    assert MIGRATION.count("coalesce(target.bid, ad_group.default_bid)") == 1
    assert len(bid_coalesces) == 1
    assert "coalesce(target.bid, ad_group.default_bid) as bid" in view
    assert "target.bid as own_bid" in view
    assert [_output_name(" ".join(item.split())) for item in items + [select_list[start:]]] == TARGET_BID_COLUMNS


def test_the_target_bid_view_joins_the_latest_known_ad_group_and_reads_as_the_caller():
    view = _flat(_view(MIGRATION, "ads_target_bid"))

    assert view.startswith("create or replace view ads_target_bid with (security_invoker = true) as select ")
    assert ("left join ads_ad_group ad_group on ad_group.profile_id = target.profile_id "
            "and ad_group.ad_product = target.ad_product and ad_group.ad_group_id = target.ad_group_id;") in view
    assert "max(" not in view


def test_graduation_and_the_structure_read_their_targets_from_the_target_bid_view():
    graduation = _flat(_body(_function(MIGRATION, "graduation_targets_between")))
    structure = _flat(_body(_function(MIGRATION, "sp_structure_between")))

    assert "from ads_target_bid target" in graduation and "from ads_target_bid target" in structure
    assert ("join latest_targets on latest_targets.ad_product = target.ad_product "
            "and latest_targets.seen_at = target.seen_at") in graduation
    # Targets go through the view, which keeps collate "C" and the campaign index (16 s vs 0.05 s, 2026-09-22).
    assert "ads_target target" not in graduation and "ads_target target" not in structure


def test_graduation_leaves_out_targets_of_paused_ad_groups_but_not_of_ad_groups_never_listed():
    graduation = _flat(_body(_function(MIGRATION, "graduation_targets_between")))

    assert ("where target.profile_id = p_profile_id and target.state = 'ENABLED' "
            "and target.ad_group_state in ('', 'ENABLED')") in graduation
    for cte in ("latest_targets as (", "latest_campaigns as (", "live_campaigns as (", "reported_products as (",
                "activity as ("):
        assert cte in graduation


def test_the_structure_read_takes_optional_families_and_campaigns_and_returns_the_agreed_columns():
    statement = _function(MIGRATION, "sp_structure_between")

    assert _flat(statement).startswith(
        "create or replace function sp_structure_between(p_profile_id text, p_from date, p_to date, "
        "p_entities text[] default null, p_campaign_ids text[] default null) returns table (")
    assert _returns_columns(statement) == STRUCTURE_COLUMNS
    assert "language sql\nstable\nas $$" in statement
    assert "security definer" not in MIGRATION


@pytest.mark.parametrize("branch", UNION_BRANCHES)
def test_every_union_branch_lines_up_with_the_returned_columns_and_types_its_nulls(branch):
    items = _select_list(_cte(_body(_function(MIGRATION, "sp_structure_between")), branch))
    declared = dict(STRUCTURE_COLUMNS)

    assert [_output_name(item) for item in items] == [name for name, _ in STRUCTURE_COLUMNS]
    for item in items:
        if item.startswith("null"):
            assert item == f"null::{declared[_output_name(item)]} as {_output_name(item)}"
        if item.startswith("''"):
            assert declared[_output_name(item)] == "text"


def test_the_structure_unions_every_branch_and_leaves_the_order_to_its_reader():
    body = _flat(_body(_function(MIGRATION, "sp_structure_between")))

    assert f"structure_rows as ( select * from campaign_rows union all select * from {UNION_BRANCHES[1]}" in body
    for branch in UNION_BRANCHES[1:]:
        assert f"union all select * from {branch}" in body
    # StructureProvider orders every answer itself; sorted here, every count would sort what it only counts.
    assert body.endswith("select structure_rows.* from structure_rows; $$;")
    assert "order by" not in body


def test_every_family_but_the_negatives_reads_the_latest_listing_of_its_table():
    body = _flat(_body(_function(MIGRATION, "sp_structure_between")))

    assert "select max(listed.seen_at) from ads_campaign listed where listed.profile_id = p_profile_id)" in body
    assert "select max(listed.seen_at) from ads_product_ad listed where listed.profile_id = p_profile_id)" in body
    assert ("select max(listed.seen_at) from ads_ad_group listed where listed.profile_id = p_profile_id "
            "and listed.ad_product = 'SP')") in body
    assert ("from ads_target_bid target where target.profile_id = p_profile_id and target.ad_product = 'SP' "
            "and target.seen_at = (select max(listed.seen_at) from ads_target listed "
            "where listed.profile_id = p_profile_id and listed.ad_product = 'SP')") in body
    assert "from ads_negative listed" not in body


def test_the_negatives_are_what_the_last_complete_run_saw_and_none_before_the_first_one():
    negatives = _flat(_cte(_body(_function(MIGRATION, "sp_structure_between")), "listed_negatives"))

    assert "where negative.profile_id = p_profile_id and negative.ad_product = 'SP'" in negatives
    assert ("join ads_listing_snapshot snapshot on snapshot.profile_id = p_profile_id "
            "and snapshot.listing = 'sp_negatives' and negative.seen_at >= snapshot.seen_at") in negatives
    assert "left join" not in negatives and "max(" not in negatives


def test_the_negatives_are_listed_when_their_last_complete_run_began_not_when_a_run_under_way_stamped_them():
    body = _body(_function(MIGRATION, "sp_structure_between"))
    negatives = _flat(_cte(body, "listed_negatives"))
    negative_rows = _select_list(_cte(body, "negative_rows"))

    assert negatives.startswith("select negative.*, snapshot.seen_at as listed_at,")
    assert negative_rows[-1] == "negative.listed_at"
    assert not any("negative.seen_at" in item for item in negative_rows)


def test_every_family_can_be_narrowed_to_any_of_several_campaigns():
    body = _flat(_body(_function(MIGRATION, "sp_structure_between")))

    for row in ("campaign", "ad_group", "target", "product_ad", "negative"):
        assert f"(p_campaign_ids is null or {row}.campaign_id = any (p_campaign_ids))" in body
    assert body.count("p_campaign_ids is null or") == 5


def test_every_family_is_guarded_by_the_requested_entities():
    body = _flat(_body(_function(MIGRATION, "sp_structure_between")))

    for family in ("campaign", "bidding_adjustment", "ad_group", "product_ad"):
        assert f"p_entities is null or '{family}' = any (p_entities)" in body
    assert "p_entities is null or target.entity = any (p_entities)" in body
    assert "p_entities is null or negative.entity = any (p_entities)" in body
    assert ("case when target.target_kind = 'keyword' then 'keyword' else 'product_targeting' end as entity"
            in body)
    for entity in ENTITY_ORDER[6:]:
        assert f"'{entity}'" in body


def test_the_placement_rows_come_from_the_four_campaign_columns_that_are_known():
    body = _flat(_body(_function(MIGRATION, "sp_structure_between")))

    assert ("cross join lateral (values ('PLACEMENT_TOP', campaign.placement_top_pct), "
            "('PLACEMENT_PRODUCT_PAGE', campaign.placement_product_page_pct), "
            "('PLACEMENT_REST_OF_SEARCH', campaign.placement_rest_of_search_pct), "
            "('SITE_AMAZON_BUSINESS', campaign.amazon_business_pct)) as adjustment (placement, percentage)") in body
    assert "where adjustment.percentage is not null" in body


def test_the_counts_count_each_family_through_the_structure_read_so_the_listing_rules_live_once():
    statement = _function(MIGRATION, "sp_structure_counts")
    body = _flat(_body(statement))

    assert _flat(statement).startswith(
        "create or replace function sp_structure_counts(p_profile_id text, p_from date, p_to date, "
        "p_campaign_ids text[] default null) returns table (")
    assert _returns_columns(statement) == [("entity", "text"), ("entity_rows", "bigint"),
                                           ("listed_at", "timestamptz")]
    assert "language sql\nstable\nas $$" in statement
    assert "from sp_structure_between(p_profile_id, p_from, p_to, null, p_campaign_ids) structure" in body
    assert "select structure.entity, count(*) as entity_rows, max(structure.listed_at) as listed_at" in body
    assert "group by structure.entity )" in body
    # The only table it reads is the snapshot, for the negatives' zeros below; no row is counted outside the read.
    assert re.findall(r"\bads_\w+", body) == ["ads_listing_snapshot"]


def test_a_complete_negatives_run_counts_its_four_families_even_at_zero():
    body = _flat(_body(_function(MIGRATION, "sp_structure_counts")))
    families = ", ".join(f"'{entity}'" for entity in ENTITY_ORDER[6:])

    assert "select counted.entity, counted.entity_rows, counted.listed_at from counted union all" in body
    assert (f"select family.entity, 0::bigint, snapshot.seen_at from ads_listing_snapshot snapshot "
            f"cross join unnest(array[{families}]) as family (entity) "
            "where snapshot.profile_id = p_profile_id and snapshot.listing = 'sp_negatives' "
            "and not exists (select 1 from counted where counted.entity = family.entity);") in body


def test_the_grants_revoke_the_defaults_first_let_the_app_read_and_the_worker_write():
    flat = _flat(MIGRATION)
    first_grant = MIGRATION.index("\ngrant ")

    assert MIGRATION.index("revoke all on ads_ad_group, ads_negative, ads_listing_snapshot, ads_target_bid "
                           "from web_user;") < first_grant
    assert MIGRATION.index("\nrevoke all on function sp_structure_between(") < first_grant
    assert ("revoke all on function sp_structure_between(text, date, date, text[], text[]), "
            "sp_structure_counts(text, date, date, text[]) from public, web_user;") in flat
    assert "grant select on ads_ad_group, ads_negative, ads_listing_snapshot, ads_target_bid to web_user;" in flat
    assert ("grant execute on function sp_structure_between(text, date, date, text[], text[]), "
            "sp_structure_counts(text, date, date, text[]) to web_user;") in flat
    assert "grant select, insert, update, delete on ads_ad_group, ads_negative to integ_worker;" in flat
    assert "grant select, insert, update on ads_listing_snapshot to integ_worker;" in flat
    assert "ai_worker" not in MIGRATION


def test_the_migration_is_additive_and_reloads_the_postgrest_schema():
    assert "drop " not in MIGRATION.lower()
    assert MIGRATION.index("begin;") < MIGRATION.index("commit;")
    assert MIGRATION.rstrip().endswith("notify pgrst, 'reload schema';")


def test_the_read_only_smoke_probes_the_new_tables_and_the_new_columns():
    tables = next(ast.literal_eval(node.value) for node in ast.walk(ast.parse(SMOKE))
                  if isinstance(node, ast.Assign) and [target.id for target in node.targets] == ["TABLES"])

    assert {("ads_ad_group", "profile_id"), ("ads_negative", "profile_id"),
            ("ads_campaign", "placement_top_pct"), ("ads_listing_snapshot", "profile_id"),
            ("integration_sync_jobs", "progress")} <= set(tables)

-- 023 — Seller Central data: the Business Report (by date and by child ASIN) and Search Query Performance, uploaded
-- by hand today and brought by SP-API later, through one write path.
--
-- Additive. A seller account is the Amazon Ads account of one marketplace (ads_entity_id + marketplace_id); its SP-API
-- selling_partner_id stays null until it is verified. The app writes through the upload_* functions (source 'manual'),
-- the SP-API worker through the save_* ones, and both land in seller_report_save. Every change of a period keeps the
-- version it replaced or deleted, so a load can be undone. The rules are in docs/seller-central-data.md.

begin;

create table if not exists seller_accounts (
    id                        serial primary key,
    -- The Amazon Ads account of this marketplace: integration_accounts.cuenta_externa_id and its profile's marketplace.
    ads_entity_id             text not null collate "C",
    marketplace_id            text not null collate "C",
    country_code              text not null default '',
    account_name              text not null default '',
    -- That SP-API's selling_partner_id equals the Ads entity id is not documented: null until confirmed.
    selling_partner_id        text collate "C",
    selling_partner_id_source text not null default ''
                              check (selling_partner_id_source in ('', 'sp_api', 'manual')),
    created_by                text not null default '',
    updated_by                text not null default '',
    created_at                timestamptz not null default now(),
    updated_at                timestamptz not null default now(),
    unique (ads_entity_id, marketplace_id),
    unique (selling_partner_id, marketplace_id),
    constraint seller_accounts_partner_id_source
        check ((selling_partner_id is null) = (selling_partner_id_source = ''))
);


-- One row per write: a save of rows or a delete of periods, by hand or by SP-API.
create table if not exists seller_report_loads (
    id                bigserial primary key,
    seller_account_id integer not null references seller_accounts (id) on delete cascade,
    dataset           text not null
                      check (dataset in ('sales_traffic_daily', 'sales_traffic_by_asin', 'sqp_brand_view',
                                         'sqp_asin_view')),
    action            text not null check (action in ('save', 'delete')),
    source            text not null check (source in ('manual', 'sp_api')),
    file_name         text not null default '',
    loaded_by         text not null default '',
    period_count      integer not null,
    created_at        timestamptz not null default now(),
    reverted_at       timestamptz,
    reverted_by       text not null default ''
);
create index if not exists seller_report_loads_account_idx
    on seller_report_loads (seller_account_id, created_at desc);


-- What each period holds now and which load wrote it: the coverage of an account.
create table if not exists seller_report_periods (
    seller_account_id integer not null references seller_accounts (id) on delete cascade,
    dataset           text not null
                      check (dataset in ('sales_traffic_daily', 'sales_traffic_by_asin', 'sqp_brand_view',
                                         'sqp_asin_view')),
    -- The SQP brand (Brand View) or ASIN (ASIN View); empty for the Business Report.
    brand_or_asin     text not null default '' collate "C",
    period_start      date not null,
    period_end        date not null,
    period_type       text not null check (period_type in ('day', 'range', 'week', 'month')),
    source            text not null check (source in ('manual', 'sp_api')),
    row_count         integer not null,
    content_sha256    text not null,
    load_id           bigint not null references seller_report_loads (id),
    primary key (seller_account_id, dataset, brand_or_asin, period_start, period_end),
    check (period_end >= period_start)
);


-- The version a change replaced or deleted, one per period and change: undoing the change puts it back.
create table if not exists seller_report_period_history (
    seller_account_id  integer not null references seller_accounts (id) on delete cascade,
    dataset            text not null,
    brand_or_asin      text not null default '' collate "C",
    period_start       date not null,
    period_end         date not null,
    changed_by_load_id bigint not null references seller_report_loads (id) on delete cascade,
    -- All null when the period was empty before the change.
    period_type        text,
    source             text,
    row_count          integer,
    content_sha256     text,
    load_id            bigint references seller_report_loads (id),
    period_rows        jsonb,
    primary key (seller_account_id, dataset, brand_or_asin, period_start, period_end, changed_by_load_id)
);
create index if not exists seller_report_period_history_load_idx
    on seller_report_period_history (changed_by_load_id);


-- The Business Report by date and SP-API's salesAndTrafficByDate, one row per day. Metrics named as SP-API names
-- them; null means the export did not bring that column. Ratios the stored counts give (CVR, averages, refund rate)
-- are left to the readers.
create table if not exists seller_sales_traffic_daily (
    seller_account_id          integer not null references seller_accounts (id) on delete cascade,
    day                        date not null,
    currency_code              text,
    ordered_product_sales      numeric(14,2),
    ordered_product_sales_b2b  numeric(14,2),
    units_ordered              integer,
    units_ordered_b2b          integer,
    total_order_items          integer,
    total_order_items_b2b      integer,
    units_refunded             integer,
    claims_granted             integer,
    claims_amount              numeric(14,2),
    shipped_product_sales      numeric(14,2),
    units_shipped              integer,
    orders_shipped             integer,
    page_views                 integer,
    page_views_b2b             integer,
    browser_page_views         integer,
    browser_page_views_b2b     integer,
    mobile_app_page_views      integer,
    mobile_app_page_views_b2b  integer,
    sessions                   integer,
    sessions_b2b               integer,
    browser_sessions           integer,
    browser_sessions_b2b       integer,
    mobile_app_sessions        integer,
    mobile_app_sessions_b2b    integer,
    buy_box_percentage         numeric(7,4),
    buy_box_percentage_b2b     numeric(7,4),
    average_offer_count        numeric(12,2),
    average_parent_items       numeric(12,2),
    feedback_received          integer,
    negative_feedback_received integer,
    primary key (seller_account_id, day)
);


-- The Business Report by child ASIN and SP-API's salesAndTrafficByAsin: one total per ASIN over an exact range, which
-- the file does not split into days. A range from SP-API can be a single day.
create table if not exists seller_sales_traffic_by_asin (
    seller_account_id                   integer not null references seller_accounts (id) on delete cascade,
    range_start                         date not null,
    range_end                           date not null,
    child_asin                          text not null collate "C",
    parent_asin                         text collate "C",
    title                               text,
    currency_code                       text,
    units_ordered                       integer,
    units_ordered_b2b                   integer,
    ordered_product_sales               numeric(14,2),
    ordered_product_sales_b2b           numeric(14,2),
    total_order_items                   integer,
    total_order_items_b2b               integer,
    sessions                            integer,
    sessions_b2b                        integer,
    browser_sessions                    integer,
    browser_sessions_b2b                integer,
    mobile_app_sessions                 integer,
    mobile_app_sessions_b2b             integer,
    session_percentage                  numeric(7,4),
    session_percentage_b2b              numeric(7,4),
    browser_session_percentage          numeric(7,4),
    browser_session_percentage_b2b      numeric(7,4),
    mobile_app_session_percentage       numeric(7,4),
    mobile_app_session_percentage_b2b   numeric(7,4),
    page_views                          integer,
    page_views_b2b                      integer,
    browser_page_views                  integer,
    browser_page_views_b2b              integer,
    mobile_app_page_views               integer,
    mobile_app_page_views_b2b           integer,
    page_views_percentage               numeric(7,4),
    page_views_percentage_b2b           numeric(7,4),
    browser_page_views_percentage       numeric(7,4),
    browser_page_views_percentage_b2b   numeric(7,4),
    mobile_app_page_views_percentage    numeric(7,4),
    mobile_app_page_views_percentage_b2b numeric(7,4),
    buy_box_percentage                  numeric(7,4),
    buy_box_percentage_b2b              numeric(7,4),
    primary key (seller_account_id, range_start, range_end, child_asin),
    check (range_end >= range_start)
);


-- Search Query Performance, Brand View and ASIN View. Counts as Amazon gives them: shares (own / total) and rates
-- (total / search query volume) are left to the readers.
create table if not exists seller_search_query_performance (
    seller_account_id                      integer not null references seller_accounts (id) on delete cascade,
    view                                   text not null check (view in ('brand', 'asin')),
    brand_or_asin                          text not null collate "C",
    period_type                            text not null check (period_type in ('week', 'month')),
    period_start                           date not null,
    period_end                             date not null,
    search_query                           text not null collate "C",
    search_query_score                     integer,
    search_query_volume                    bigint,
    total_impression_count                 bigint,
    own_impression_count                   bigint,
    total_click_count                      bigint,
    own_click_count                        bigint,
    total_median_click_price               numeric(14,2),
    own_median_click_price                 numeric(14,2),
    total_same_day_shipping_click_count    bigint,
    total_one_day_shipping_click_count     bigint,
    total_two_day_shipping_click_count     bigint,
    total_cart_add_count                   bigint,
    own_cart_add_count                     bigint,
    total_median_cart_add_price            numeric(14,2),
    own_median_cart_add_price              numeric(14,2),
    total_same_day_shipping_cart_add_count bigint,
    total_one_day_shipping_cart_add_count  bigint,
    total_two_day_shipping_cart_add_count  bigint,
    total_purchase_count                   bigint,
    own_purchase_count                     bigint,
    total_median_purchase_price            numeric(14,2),
    own_median_purchase_price              numeric(14,2),
    total_same_day_shipping_purchase_count bigint,
    total_one_day_shipping_purchase_count  bigint,
    total_two_day_shipping_purchase_count  bigint,
    currency_code                          text,
    primary key (seller_account_id, view, brand_or_asin, period_type, period_start, search_query)
);


-- What a write did, or would do in a preview, to one period; existing_* describe the period before the call.
do $$ begin
    if not exists (select 1 from pg_type
                    where typname = 'seller_report_change' and typnamespace = 'public'::regnamespace) then
        create type seller_report_change as (
            period_start       date,
            period_end         date,
            brand_or_asin      text,
            status             text,
            row_count          integer,
            existing_source    text,
            existing_row_count integer,
            existing_loaded_by text,
            existing_loaded_at timestamptz,
            existing_file_name text,
            load_id            bigint
        );
    end if;
end $$;


-- ── helpers: only the functions below call them ─────────────────────────────

create or replace function seller_report_reject(p_code text, p_detail text)
returns void
language plpgsql
as $$
begin
    raise exception using errcode = 'P0001', message = 'seller_report.' || p_code, detail = coalesce(p_detail, '');
end;
$$;


create or replace function seller_report_table(p_dataset text)
returns regclass
language sql
stable
as $$
    select case p_dataset
        when 'sales_traffic_daily' then 'seller_sales_traffic_daily'::regclass
        when 'sales_traffic_by_asin' then 'seller_sales_traffic_by_asin'::regclass
        when 'sqp_brand_view' then 'seller_search_query_performance'::regclass
        when 'sqp_asin_view' then 'seller_search_query_performance'::regclass
    end;
$$;


-- The columns a period's arguments fill; a row never carries them.
create or replace function seller_report_argument_columns(p_dataset text)
returns text[]
language sql
immutable
as $$
    select case p_dataset
        when 'sales_traffic_daily' then array['seller_account_id']
        when 'sales_traffic_by_asin' then array['seller_account_id', 'range_start', 'range_end']
        when 'sqp_brand_view' then array['seller_account_id', 'view', 'brand_or_asin', 'period_type', 'period_start',
                                         'period_end']
        when 'sqp_asin_view' then array['seller_account_id', 'view', 'brand_or_asin', 'period_type', 'period_start',
                                        'period_end']
    end;
$$;


create or replace function seller_report_sqp_view(p_dataset text)
returns text
language sql
immutable
as $$
    select case p_dataset when 'sqp_brand_view' then 'brand' when 'sqp_asin_view' then 'asin' end;
$$;


create or replace function seller_report_check_source(p_source text)
returns void
language plpgsql
as $$
begin
    if p_source is null or p_source not in ('manual', 'sp_api') then
        perform seller_report_reject('invalid_source', format('unknown source %s', coalesce(p_source, 'null')));
    end if;
end;
$$;


create or replace function seller_report_lock_account(p_account_id integer)
returns void
language plpgsql
as $$
begin
    -- The writes of one account go one at a time: two uploads of the same period must not interleave.
    perform 1 from seller_accounts where id = p_account_id for update;
    if not found then
        perform seller_report_reject('unknown_account', format('seller account %s does not exist', p_account_id));
    end if;
end;
$$;


create or replace function seller_report_check_rows(p_dataset text, p_rows jsonb)
returns void
language plpgsql
as $$
declare
    unknown_columns text;
begin
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        perform seller_report_reject('rows_not_an_array', 'the rows must be a json array');
    end if;
    if jsonb_array_length(p_rows) = 0 then
        perform seller_report_reject('no_rows', 'there are no rows to save');
    end if;
    if exists (select 1 from jsonb_array_elements(p_rows) row_data where jsonb_typeof(row_data) <> 'object') then
        perform seller_report_reject('row_not_an_object', 'every row must be a json object');
    end if;
    -- jsonb_populate_recordset drops a misspelled key without a word, and its column would stay null for good.
    select string_agg(distinct field, ', ' order by field) into unknown_columns
      from jsonb_array_elements(p_rows) row_data
     cross join lateral jsonb_object_keys(row_data) field
     where field = any (seller_report_argument_columns(p_dataset))
        or not exists (select 1 from pg_attribute table_column
                        where table_column.attrelid = seller_report_table(p_dataset)
                          and table_column.attname = field
                          and table_column.attnum > 0 and not table_column.attisdropped);
    if unknown_columns is not null then
        perform seller_report_reject('unknown_columns', unknown_columns);
    end if;
    begin
        if p_dataset = 'sales_traffic_daily' then
            perform count(*) from jsonb_populate_recordset(null::seller_sales_traffic_daily, p_rows);
        elsif p_dataset = 'sales_traffic_by_asin' then
            perform count(*) from jsonb_populate_recordset(null::seller_sales_traffic_by_asin, p_rows);
        else
            perform count(*) from jsonb_populate_recordset(null::seller_search_query_performance, p_rows);
        end if;
    exception when data_exception then
        perform seller_report_reject('invalid_value', sqlerrm);
    end;
end;
$$;


create or replace function seller_report_check_range(p_first_day date, p_last_day date)
returns void
language plpgsql
as $$
begin
    if p_first_day is null or p_last_day is null then
        perform seller_report_reject('missing_range', 'the range needs its first and last day');
    end if;
    if p_last_day < p_first_day then
        perform seller_report_reject('reversed_range', format('%s is before %s', p_last_day, p_first_day));
    end if;
    -- Tomorrow in UTC is today somewhere Amazon sells; later than that is a wrong date.
    if p_last_day > current_date + 1 then
        perform seller_report_reject('future_period', p_last_day::text);
    end if;
end;
$$;


-- Amazon's SQP periods: a week from Sunday to Saturday, or a calendar month.
create or replace function seller_report_sqp_period_end(p_period_type text, p_period_start date)
returns date
language plpgsql
as $$
begin
    if p_period_start is null then
        perform seller_report_reject('missing_period', 'the period needs its first day');
    end if;
    if p_period_type = 'week' then
        if extract(isodow from p_period_start) <> 7 then
            perform seller_report_reject('week_not_on_sunday', p_period_start::text);
        end if;
        return p_period_start + 6;
    end if;
    if p_period_type = 'month' then
        if extract(day from p_period_start) <> 1 then
            perform seller_report_reject('month_not_on_first_day', p_period_start::text);
        end if;
        return (p_period_start + interval '1 month' - interval '1 day')::date;
    end if;
    perform seller_report_reject('invalid_period_type', coalesce(p_period_type, 'null'));
    return null;
end;
$$;


-- A period's rows as a json array without the argument columns, in key order: the shape a save receives, keeps in
-- the history and hashes.
create or replace function seller_report_period_rows(p_account_id integer, p_dataset text, p_brand_or_asin text,
                                                     p_period_start date, p_period_end date)
returns jsonb
language sql
stable
as $$
    select case
        when p_dataset = 'sales_traffic_daily' then (
            select coalesce(jsonb_agg(to_jsonb(daily) - seller_report_argument_columns(p_dataset) order by daily.day),
                            '[]'::jsonb)
              from seller_sales_traffic_daily daily
             where daily.seller_account_id = p_account_id and daily.day = p_period_start)
        when p_dataset = 'sales_traffic_by_asin' then (
            select coalesce(jsonb_agg(to_jsonb(by_asin) - seller_report_argument_columns(p_dataset)
                                      order by by_asin.child_asin collate "C"), '[]'::jsonb)
              from seller_sales_traffic_by_asin by_asin
             where by_asin.seller_account_id = p_account_id
               and by_asin.range_start = p_period_start and by_asin.range_end = p_period_end)
        else (
            select coalesce(jsonb_agg(to_jsonb(query_row) - seller_report_argument_columns(p_dataset)
                                      order by query_row.search_query collate "C"), '[]'::jsonb)
              from seller_search_query_performance query_row
             where query_row.seller_account_id = p_account_id
               and query_row.view = seller_report_sqp_view(p_dataset)
               and query_row.brand_or_asin = p_brand_or_asin
               and query_row.period_start = p_period_start and query_row.period_end = p_period_end)
    end;
$$;


-- Replaces a period's rows with the given ones; null or an empty array leaves the period without rows.
create or replace function seller_report_write_period(p_account_id integer, p_dataset text, p_brand_or_asin text,
                                                      p_period_type text, p_period_start date, p_period_end date,
                                                      p_period_rows jsonb)
returns void
language plpgsql
as $$
begin
    if p_dataset = 'sales_traffic_daily' then
        delete from seller_sales_traffic_daily
         where seller_account_id = p_account_id and day = p_period_start;
        insert into seller_sales_traffic_daily
        select typed.*
          from jsonb_array_elements(coalesce(p_period_rows, '[]'::jsonb)) row_data
         cross join lateral jsonb_populate_record(
               null::seller_sales_traffic_daily,
               row_data || jsonb_build_object('seller_account_id', p_account_id)) typed;
    elsif p_dataset = 'sales_traffic_by_asin' then
        delete from seller_sales_traffic_by_asin
         where seller_account_id = p_account_id and range_start = p_period_start and range_end = p_period_end;
        insert into seller_sales_traffic_by_asin
        select typed.*
          from jsonb_array_elements(coalesce(p_period_rows, '[]'::jsonb)) row_data
         cross join lateral jsonb_populate_record(
               null::seller_sales_traffic_by_asin,
               row_data || jsonb_build_object('seller_account_id', p_account_id, 'range_start', p_period_start,
                                              'range_end', p_period_end)) typed;
    else
        delete from seller_search_query_performance
         where seller_account_id = p_account_id and view = seller_report_sqp_view(p_dataset)
           and brand_or_asin = p_brand_or_asin and period_type = p_period_type and period_start = p_period_start;
        insert into seller_search_query_performance
        select typed.*
          from jsonb_array_elements(coalesce(p_period_rows, '[]'::jsonb)) row_data
         cross join lateral jsonb_populate_record(
               null::seller_search_query_performance,
               row_data || jsonb_build_object('seller_account_id', p_account_id,
                                              'view', seller_report_sqp_view(p_dataset),
                                              'brand_or_asin', p_brand_or_asin, 'period_type', p_period_type,
                                              'period_start', p_period_start, 'period_end', p_period_end)) typed;
    end if;
end;
$$;


-- Pushes the period's current version, or that it was empty, before the load changes it.
create or replace function seller_report_keep_version(p_account_id integer, p_dataset text, p_brand_or_asin text,
                                                      p_period_start date, p_period_end date,
                                                      p_changed_by_load_id bigint)
returns void
language sql
as $$
    insert into seller_report_period_history (
        seller_account_id, dataset, brand_or_asin, period_start, period_end, changed_by_load_id, period_type, source,
        row_count, content_sha256, load_id, period_rows
    )
    select p_account_id, p_dataset, p_brand_or_asin, p_period_start, p_period_end, p_changed_by_load_id,
           existing.period_type, existing.source, existing.row_count, existing.content_sha256, existing.load_id,
           case when existing.load_id is not null
                then seller_report_period_rows(p_account_id, p_dataset, p_brand_or_asin, p_period_start, p_period_end)
           end
      from (values (true)) as anchor (one_row)
      left join seller_report_periods existing
             on existing.seller_account_id = p_account_id and existing.dataset = p_dataset
            and existing.brand_or_asin = p_brand_or_asin
            and existing.period_start = p_period_start and existing.period_end = p_period_end;
$$;


create or replace function seller_report_open_load(p_account_id integer, p_dataset text, p_action text,
                                                   p_source text, p_loaded_by text, p_file_name text,
                                                   p_period_count integer)
returns bigint
language sql
as $$
    insert into seller_report_loads (seller_account_id, dataset, action, source, loaded_by, file_name, period_count)
    values (p_account_id, p_dataset, p_action, p_source, coalesce(p_loaded_by, ''), coalesce(p_file_name, ''),
            p_period_count)
    returning id;
$$;


-- Touching SP-API data by hand is the one change that asks first.
create or replace function seller_report_needs_confirmation(p_existing_source text, p_source text,
                                                            p_replace_api_data boolean)
returns boolean
language sql
immutable
as $$
    select coalesce(p_existing_source, '') = 'sp_api' and p_source = 'manual'
       and not coalesce(p_replace_api_data, false);
$$;


create or replace function seller_report_save_status(p_existing_source text, p_existing_sha256 text,
                                                     p_source text, p_sha256 text, p_replace_api_data boolean)
returns text
language sql
immutable
as $$
    select case
        when p_existing_source is null then 'inserted'
        when p_existing_sha256 = p_sha256 then 'unchanged'
        when seller_report_needs_confirmation(p_existing_source, p_source, p_replace_api_data) then 'conflict'
        else 'replaced'
    end;
$$;


-- The one write of every dataset and source. p_periods: [{period_start, period_end, period_type, brand_or_asin,
-- period_rows}], each period_rows already in the shape seller_report_period_rows returns.
create or replace function seller_report_save(p_account_id integer, p_dataset text, p_source text, p_periods jsonb,
                                              p_replace_api_data boolean, p_preview boolean, p_loaded_by text,
                                              p_file_name text)
returns setof seller_report_change
language plpgsql
as $$
declare
    planned       seller_report_change[] := '{}';
    planned_types text[] := '{}';
    planned_rows  jsonb[] := '{}';
    planned_hash  text[] := '{}';
    incoming      record;
    change        seller_report_change;
    new_load_id   bigint;
    slot_index    integer;
begin
    for incoming in
        select incoming_period.period_start, incoming_period.period_end, incoming_period.period_type,
               incoming_period.brand_or_asin, incoming_period.period_rows,
               encode(sha256(convert_to(incoming_period.period_rows::text, 'UTF8')), 'hex') as content_sha256,
               existing.source as existing_source, existing.content_sha256 as existing_sha256,
               existing.row_count as existing_row_count, existing_load.loaded_by as existing_loaded_by,
               existing_load.created_at as existing_loaded_at, existing_load.file_name as existing_file_name
          from jsonb_to_recordset(p_periods) as incoming_period (period_start date, period_end date,
                                                                 period_type text, brand_or_asin text,
                                                                 period_rows jsonb)
          left join seller_report_periods existing
                 on existing.seller_account_id = p_account_id and existing.dataset = p_dataset
                and existing.brand_or_asin = incoming_period.brand_or_asin
                and existing.period_start = incoming_period.period_start
                and existing.period_end = incoming_period.period_end
          left join seller_report_loads existing_load on existing_load.id = existing.load_id
         order by incoming_period.period_start, incoming_period.period_end
    loop
        change := (incoming.period_start, incoming.period_end, incoming.brand_or_asin,
                   seller_report_save_status(incoming.existing_source, incoming.existing_sha256, p_source,
                                             incoming.content_sha256, p_replace_api_data),
                   jsonb_array_length(incoming.period_rows), incoming.existing_source, incoming.existing_row_count,
                   incoming.existing_loaded_by, incoming.existing_loaded_at, incoming.existing_file_name, null);
        planned := array_append(planned, change);
        planned_types := array_append(planned_types, incoming.period_type);
        planned_rows := array_append(planned_rows, incoming.period_rows);
        planned_hash := array_append(planned_hash, incoming.content_sha256);
    end loop;

    -- One period that needs confirmation holds back the whole load: nothing is written and every period says why.
    if p_preview
       or exists (select 1 from unnest(planned) planned_change where planned_change.status = 'conflict')
       or not exists (select 1 from unnest(planned) planned_change
                       where planned_change.status in ('inserted', 'replaced')) then
        return query select * from unnest(planned);
        return;
    end if;

    new_load_id := seller_report_open_load(
        p_account_id, p_dataset, 'save', p_source, p_loaded_by, p_file_name,
        (select count(*)::integer from unnest(planned) planned_change
          where planned_change.status in ('inserted', 'replaced')));

    for slot_index in 1 .. array_length(planned, 1) loop
        change := planned[slot_index];
        continue when change.status not in ('inserted', 'replaced');
        perform seller_report_keep_version(p_account_id, p_dataset, change.brand_or_asin, change.period_start,
                                           change.period_end, new_load_id);
        perform seller_report_write_period(p_account_id, p_dataset, change.brand_or_asin, planned_types[slot_index],
                                           change.period_start, change.period_end, planned_rows[slot_index]);
        insert into seller_report_periods (seller_account_id, dataset, brand_or_asin, period_start, period_end,
                                           period_type, source, row_count, content_sha256, load_id)
        values (p_account_id, p_dataset, change.brand_or_asin, change.period_start, change.period_end,
                planned_types[slot_index], p_source, change.row_count, planned_hash[slot_index], new_load_id)
        on conflict (seller_account_id, dataset, brand_or_asin, period_start, period_end) do update
           set period_type = excluded.period_type, source = excluded.source, row_count = excluded.row_count,
               content_sha256 = excluded.content_sha256, load_id = excluded.load_id;
        change.load_id := new_load_id;
        planned[slot_index] := change;
    end loop;

    return query select * from unnest(planned);
end;
$$;


-- ── writes: the SP-API worker calls save_*, the app calls upload_* ───────────

create or replace function save_seller_sales_traffic_daily(p_account_id integer, p_rows jsonb, p_source text,
                                                          p_replace_api_data boolean default false,
                                                          p_preview boolean default false,
                                                          p_loaded_by text default '', p_file_name text default '')
returns setof seller_report_change
language plpgsql
security definer
set search_path = public, pg_temp
set statement_timeout = '120s'
as $$
declare
    problem_day date;
begin
    perform seller_report_check_source(p_source);
    perform seller_report_lock_account(p_account_id);
    perform seller_report_check_rows('sales_traffic_daily', p_rows);

    if exists (select 1 from jsonb_populate_recordset(null::seller_sales_traffic_daily, p_rows) typed
                where typed.day is null) then
        perform seller_report_reject('missing_day', 'every row needs its day');
    end if;
    select typed.day into problem_day
      from jsonb_populate_recordset(null::seller_sales_traffic_daily, p_rows) typed
     group by typed.day having count(*) > 1
     order by typed.day
     limit 1;
    if problem_day is not null then
        perform seller_report_reject('duplicate_day', problem_day::text);
    end if;
    select max(typed.day) into problem_day
      from jsonb_populate_recordset(null::seller_sales_traffic_daily, p_rows) typed;
    if problem_day > current_date + 1 then
        perform seller_report_reject('future_period', problem_day::text);
    end if;

    return query
    select * from seller_report_save(
        p_account_id, 'sales_traffic_daily', p_source,
        (select jsonb_agg(jsonb_build_object(
                    'period_start', typed.day, 'period_end', typed.day, 'period_type', 'day', 'brand_or_asin', '',
                    'period_rows', jsonb_build_array(
                        to_jsonb(typed) - seller_report_argument_columns('sales_traffic_daily')))
                order by typed.day)
           from jsonb_populate_recordset(null::seller_sales_traffic_daily, p_rows) typed),
        p_replace_api_data, p_preview, p_loaded_by, p_file_name);
end;
$$;


create or replace function save_seller_sales_traffic_by_asin(p_account_id integer, p_range_start date,
                                                            p_range_end date, p_rows jsonb, p_source text,
                                                            p_replace_api_data boolean default false,
                                                            p_preview boolean default false,
                                                            p_loaded_by text default '', p_file_name text default '')
returns setof seller_report_change
language plpgsql
security definer
set search_path = public, pg_temp
set statement_timeout = '120s'
as $$
declare
    problem_asin text;
begin
    perform seller_report_check_source(p_source);
    perform seller_report_lock_account(p_account_id);
    perform seller_report_check_range(p_range_start, p_range_end);
    perform seller_report_check_rows('sales_traffic_by_asin', p_rows);

    select coalesce(typed.child_asin, 'null') into problem_asin
      from jsonb_populate_recordset(null::seller_sales_traffic_by_asin, p_rows) typed
     where typed.child_asin is null or typed.child_asin !~ '^[A-Z0-9]{10}$'
     limit 1;
    if problem_asin is not null then
        perform seller_report_reject('invalid_asin', problem_asin);
    end if;
    select typed.child_asin into problem_asin
      from jsonb_populate_recordset(null::seller_sales_traffic_by_asin, p_rows) typed
     group by typed.child_asin having count(*) > 1
     order by typed.child_asin
     limit 1;
    if problem_asin is not null then
        perform seller_report_reject('duplicate_asin', problem_asin);
    end if;

    return query
    select * from seller_report_save(
        p_account_id, 'sales_traffic_by_asin', p_source,
        jsonb_build_array(jsonb_build_object(
            'period_start', p_range_start, 'period_end', p_range_end, 'period_type', 'range', 'brand_or_asin', '',
            'period_rows', (select jsonb_agg(to_jsonb(typed) - seller_report_argument_columns('sales_traffic_by_asin')
                                             order by typed.child_asin collate "C")
                              from jsonb_populate_recordset(null::seller_sales_traffic_by_asin, p_rows) typed))),
        p_replace_api_data, p_preview, p_loaded_by, p_file_name);
end;
$$;


create or replace function save_seller_search_query_performance(p_account_id integer, p_view text,
                                                               p_brand_or_asin text, p_period_type text,
                                                               p_period_start date, p_rows jsonb, p_source text,
                                                               p_replace_api_data boolean default false,
                                                               p_preview boolean default false,
                                                               p_loaded_by text default '',
                                                               p_file_name text default '')
returns setof seller_report_change
language plpgsql
security definer
set search_path = public, pg_temp
set statement_timeout = '120s'
as $$
declare
    sqp_dataset    text := case p_view when 'brand' then 'sqp_brand_view' when 'asin' then 'sqp_asin_view' end;
    sqp_period_end date;
    problem_query  text;
begin
    perform seller_report_check_source(p_source);
    perform seller_report_lock_account(p_account_id);
    if sqp_dataset is null then
        perform seller_report_reject('invalid_view', coalesce(p_view, 'null'));
    end if;
    if p_brand_or_asin is null or p_brand_or_asin = '' or p_brand_or_asin <> btrim(p_brand_or_asin) then
        perform seller_report_reject('invalid_brand_or_asin', coalesce(p_brand_or_asin, 'null'));
    end if;
    if p_view = 'asin' and p_brand_or_asin !~ '^[A-Z0-9]{10}$' then
        perform seller_report_reject('invalid_asin', p_brand_or_asin);
    end if;
    sqp_period_end := seller_report_sqp_period_end(p_period_type, p_period_start);
    if sqp_period_end > current_date + 1 then
        perform seller_report_reject('future_period', sqp_period_end::text);
    end if;
    perform seller_report_check_rows(sqp_dataset, p_rows);

    if exists (select 1 from jsonb_populate_recordset(null::seller_search_query_performance, p_rows) typed
                where coalesce(typed.search_query, '') = '') then
        perform seller_report_reject('missing_search_query', 'every row needs its search query');
    end if;
    select typed.search_query into problem_query
      from jsonb_populate_recordset(null::seller_search_query_performance, p_rows) typed
     group by typed.search_query having count(*) > 1
     order by typed.search_query
     limit 1;
    if problem_query is not null then
        perform seller_report_reject('duplicate_search_query', problem_query);
    end if;

    return query
    select * from seller_report_save(
        p_account_id, sqp_dataset, p_source,
        jsonb_build_array(jsonb_build_object(
            'period_start', p_period_start, 'period_end', sqp_period_end, 'period_type', p_period_type,
            'brand_or_asin', p_brand_or_asin,
            'period_rows', (select jsonb_agg(to_jsonb(typed) - seller_report_argument_columns(sqp_dataset)
                                             order by typed.search_query collate "C")
                              from jsonb_populate_recordset(null::seller_search_query_performance, p_rows) typed))),
        p_replace_api_data, p_preview, p_loaded_by, p_file_name);
end;
$$;


create or replace function upload_seller_sales_traffic_daily(p_account_id integer, p_rows jsonb,
                                                            p_replace_api_data boolean default false,
                                                            p_preview boolean default false,
                                                            p_loaded_by text default '',
                                                            p_file_name text default '')
returns setof seller_report_change
language sql
security definer
set search_path = public, pg_temp
as $$
    select * from save_seller_sales_traffic_daily(p_account_id, p_rows, 'manual', p_replace_api_data, p_preview,
                                                  p_loaded_by, p_file_name);
$$;


create or replace function upload_seller_sales_traffic_by_asin(p_account_id integer, p_range_start date,
                                                              p_range_end date, p_rows jsonb,
                                                              p_replace_api_data boolean default false,
                                                              p_preview boolean default false,
                                                              p_loaded_by text default '',
                                                              p_file_name text default '')
returns setof seller_report_change
language sql
security definer
set search_path = public, pg_temp
as $$
    select * from save_seller_sales_traffic_by_asin(p_account_id, p_range_start, p_range_end, p_rows, 'manual',
                                                    p_replace_api_data, p_preview, p_loaded_by, p_file_name);
$$;


create or replace function upload_seller_search_query_performance(p_account_id integer, p_view text,
                                                                 p_brand_or_asin text, p_period_type text,
                                                                 p_period_start date, p_rows jsonb,
                                                                 p_replace_api_data boolean default false,
                                                                 p_preview boolean default false,
                                                                 p_loaded_by text default '',
                                                                 p_file_name text default '')
returns setof seller_report_change
language sql
security definer
set search_path = public, pg_temp
as $$
    select * from save_seller_search_query_performance(p_account_id, p_view, p_brand_or_asin, p_period_type,
                                                       p_period_start, p_rows, 'manual', p_replace_api_data,
                                                       p_preview, p_loaded_by, p_file_name);
$$;


-- Deletes the periods of a dataset that fall inside the range. Deleting is a load too, so it can be undone.
create or replace function delete_seller_report_periods(p_account_id integer, p_dataset text, p_brand_or_asin text,
                                                        p_first_day date, p_last_day date,
                                                        p_replace_api_data boolean default false,
                                                        p_preview boolean default false,
                                                        p_deleted_by text default '')
returns setof seller_report_change
language plpgsql
security definer
set search_path = public, pg_temp
set statement_timeout = '120s'
as $$
declare
    planned       seller_report_change[] := '{}';
    planned_types text[] := '{}';
    stored        record;
    change        seller_report_change;
    new_load_id   bigint;
    slot_index    integer;
begin
    if seller_report_argument_columns(p_dataset) is null then
        perform seller_report_reject('invalid_dataset', coalesce(p_dataset, 'null'));
    end if;
    if p_first_day is null or p_last_day is null or p_last_day < p_first_day then
        perform seller_report_reject('invalid_range', format('%s to %s', p_first_day, p_last_day));
    end if;
    perform seller_report_lock_account(p_account_id);

    for stored in
        select existing.period_start, existing.period_end, existing.period_type, existing.brand_or_asin,
               existing.source, existing.row_count, existing_load.loaded_by, existing_load.created_at,
               existing_load.file_name
          from seller_report_periods existing
          join seller_report_loads existing_load on existing_load.id = existing.load_id
         where existing.seller_account_id = p_account_id and existing.dataset = p_dataset
           and existing.brand_or_asin = coalesce(p_brand_or_asin, '')
           and existing.period_start >= p_first_day and existing.period_end <= p_last_day
         order by existing.period_start, existing.period_end
    loop
        change := (stored.period_start, stored.period_end, stored.brand_or_asin,
                   case when seller_report_needs_confirmation(stored.source, 'manual', p_replace_api_data)
                        then 'conflict' else 'deleted' end,
                   0, stored.source, stored.row_count, stored.loaded_by, stored.created_at, stored.file_name, null);
        planned := array_append(planned, change);
        planned_types := array_append(planned_types, stored.period_type);
    end loop;

    if p_preview or coalesce(array_length(planned, 1), 0) = 0
       or exists (select 1 from unnest(planned) planned_change where planned_change.status = 'conflict') then
        return query select * from unnest(planned);
        return;
    end if;

    new_load_id := seller_report_open_load(p_account_id, p_dataset, 'delete', 'manual', p_deleted_by, '',
                                           array_length(planned, 1));
    for slot_index in 1 .. array_length(planned, 1) loop
        change := planned[slot_index];
        perform seller_report_keep_version(p_account_id, p_dataset, change.brand_or_asin, change.period_start,
                                           change.period_end, new_load_id);
        perform seller_report_write_period(p_account_id, p_dataset, change.brand_or_asin, planned_types[slot_index],
                                           change.period_start, change.period_end, null);
        delete from seller_report_periods
         where seller_account_id = p_account_id and dataset = p_dataset and brand_or_asin = change.brand_or_asin
           and period_start = change.period_start and period_end = change.period_end;
        change.load_id := new_load_id;
        planned[slot_index] := change;
    end loop;

    return query select * from unnest(planned);
end;
$$;


-- Undoes a load: every period it still owns goes back to the version it replaced, or empty if it had none. A period
-- changed since by another load is skipped. Undoing the same load twice does nothing.
create or replace function revert_seller_report_load(p_load_id bigint, p_preview boolean default false,
                                                     p_reverted_by text default '')
returns setof seller_report_change
language plpgsql
security definer
set search_path = public, pg_temp
set statement_timeout = '120s'
as $$
declare
    load_to_revert   seller_report_loads%rowtype;
    previous_version record;
    change           seller_report_change;
    can_revert       boolean;
    reverted_any     boolean := false;
begin
    select * into load_to_revert from seller_report_loads where id = p_load_id;
    if not found then
        perform seller_report_reject('unknown_load', format('load %s does not exist', p_load_id));
    end if;
    perform seller_report_lock_account(load_to_revert.seller_account_id);
    -- A second click waits on that lock and finds the load already undone.
    select * into load_to_revert from seller_report_loads where id = p_load_id;
    if load_to_revert.reverted_at is not null then
        return;
    end if;

    for previous_version in
        select history.brand_or_asin, history.period_start, history.period_end, history.period_type,
               history.source, history.row_count, history.content_sha256, history.load_id, history.period_rows,
               existing.period_type as existing_period_type, existing.source as existing_source,
               existing.row_count as existing_row_count, existing.load_id as existing_load_id,
               existing_load.loaded_by as existing_loaded_by, existing_load.created_at as existing_loaded_at,
               existing_load.file_name as existing_file_name
          from seller_report_period_history history
          left join seller_report_periods existing
                 on existing.seller_account_id = history.seller_account_id and existing.dataset = history.dataset
                and existing.brand_or_asin = history.brand_or_asin
                and existing.period_start = history.period_start and existing.period_end = history.period_end
          left join seller_report_loads existing_load on existing_load.id = existing.load_id
         where history.changed_by_load_id = p_load_id
         order by history.period_start, history.period_end
    loop
        can_revert := case load_to_revert.action
                          when 'save' then previous_version.existing_load_id is not distinct from p_load_id
                          else previous_version.existing_load_id is null
                      end;
        change := (previous_version.period_start, previous_version.period_end, previous_version.brand_or_asin,
                   case when not can_revert then 'skipped'
                        when previous_version.source is null then 'removed'
                        else 'restored' end,
                   case when not can_revert then previous_version.existing_row_count
                        else coalesce(previous_version.row_count, 0) end,
                   previous_version.existing_source, previous_version.existing_row_count,
                   previous_version.existing_loaded_by, previous_version.existing_loaded_at,
                   previous_version.existing_file_name, null);
        if can_revert and not p_preview then
            perform seller_report_write_period(
                load_to_revert.seller_account_id, load_to_revert.dataset, previous_version.brand_or_asin,
                coalesce(previous_version.period_type, previous_version.existing_period_type),
                previous_version.period_start, previous_version.period_end, previous_version.period_rows);
            if previous_version.source is null then
                delete from seller_report_periods
                 where seller_account_id = load_to_revert.seller_account_id and dataset = load_to_revert.dataset
                   and brand_or_asin = previous_version.brand_or_asin
                   and period_start = previous_version.period_start and period_end = previous_version.period_end;
            else
                insert into seller_report_periods (seller_account_id, dataset, brand_or_asin, period_start,
                                                   period_end, period_type, source, row_count, content_sha256,
                                                   load_id)
                values (load_to_revert.seller_account_id, load_to_revert.dataset, previous_version.brand_or_asin,
                        previous_version.period_start, previous_version.period_end, previous_version.period_type,
                        previous_version.source, previous_version.row_count, previous_version.content_sha256,
                        previous_version.load_id)
                on conflict (seller_account_id, dataset, brand_or_asin, period_start, period_end) do update
                   set period_type = excluded.period_type, source = excluded.source,
                       row_count = excluded.row_count, content_sha256 = excluded.content_sha256,
                       load_id = excluded.load_id;
            end if;
            delete from seller_report_period_history
             where seller_account_id = load_to_revert.seller_account_id and dataset = load_to_revert.dataset
               and brand_or_asin = previous_version.brand_or_asin
               and period_start = previous_version.period_start and period_end = previous_version.period_end
               and changed_by_load_id = p_load_id;
            change.load_id := p_load_id;
            reverted_any := true;
        end if;
        return next change;
    end loop;

    if reverted_any then
        update seller_report_loads
           set reverted_at = now(), reverted_by = coalesce(p_reverted_by, '')
         where id = p_load_id;
    end if;
end;
$$;


-- ── accounts ─────────────────────────────────────────────────────────────────

-- The seller account of an Amazon Ads profile, created the first time it is asked for.
create or replace function seller_account_for_ads_profile(p_profile_id text, p_actor text default '')
returns seller_accounts
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    ads_account integration_accounts%rowtype;
    ads_profile jsonb;
    account     seller_accounts%rowtype;
begin
    select * into ads_account
      from integration_accounts
     where integration_slug = 'amazon_ads'
       and profiles @> jsonb_build_array(jsonb_build_object('profile_id', p_profile_id));
    if not found then
        perform seller_report_reject('unknown_ads_profile',
                                     format('no Amazon Ads account lists profile %s', p_profile_id));
    end if;
    if ads_account.tipo <> 'seller' then
        perform seller_report_reject('not_a_seller',
                                     format('profile %s belongs to a %s account', p_profile_id, ads_account.tipo));
    end if;
    select listed.value into ads_profile
      from jsonb_array_elements(ads_account.profiles) as listed
     where listed.value ->> 'profile_id' = p_profile_id;
    if coalesce(ads_profile ->> 'marketplace_id', '') = '' then
        perform seller_report_reject('profile_without_marketplace',
                                     format('profile %s has no marketplace', p_profile_id));
    end if;

    insert into seller_accounts (ads_entity_id, marketplace_id, country_code, account_name, created_by, updated_by)
    values (ads_account.cuenta_externa_id, ads_profile ->> 'marketplace_id',
            coalesce(ads_profile ->> 'country_code', ''), ads_account.nombre_externo, coalesce(p_actor, ''),
            coalesce(p_actor, ''))
    on conflict (ads_entity_id, marketplace_id) do nothing;

    select * into account
      from seller_accounts
     where ads_entity_id = ads_account.cuenta_externa_id and marketplace_id = ads_profile ->> 'marketplace_id';
    return account;
end;
$$;


-- Sets the SP-API seller id by hand, or clears it with null or ''.
create or replace function set_selling_partner_id(p_account_id integer, p_selling_partner_id text,
                                                  p_actor text default '')
returns seller_accounts
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    partner_id text := nullif(btrim(coalesce(p_selling_partner_id, '')), '');
    account    seller_accounts%rowtype;
begin
    if partner_id is not null and partner_id !~ '^[A-Z0-9]+$' then
        perform seller_report_reject('invalid_selling_partner_id', partner_id);
    end if;
    perform seller_report_lock_account(p_account_id);
    begin
        update seller_accounts
           set selling_partner_id = partner_id,
               selling_partner_id_source = case when partner_id is null then '' else 'manual' end,
               updated_by = coalesce(p_actor, ''),
               updated_at = now()
         where id = p_account_id
        returning * into account;
    exception when unique_violation then
        perform seller_report_reject('selling_partner_id_in_use', partner_id);
    end;
    return account;
end;
$$;


-- Deletes an account with no data left; its loads and history go with it. False if it no longer exists.
create or replace function delete_seller_account(p_account_id integer)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if not exists (select 1 from seller_accounts where id = p_account_id) then
        return false;
    end if;
    perform seller_report_lock_account(p_account_id);
    if exists (select 1 from seller_report_periods where seller_account_id = p_account_id) then
        perform seller_report_reject('account_has_data',
                                     format('seller account %s still has data: delete it first', p_account_id));
    end if;
    delete from seller_accounts where id = p_account_id;
    return true;
end;
$$;


-- ── grants ───────────────────────────────────────────────────────────────────
-- Revoke first: schema.sql gives web_user CRUD on every new table and sequence, and Postgres gives public EXECUTE on
-- every new function.
revoke all on seller_accounts, seller_report_loads, seller_report_periods, seller_report_period_history,
              seller_sales_traffic_daily, seller_sales_traffic_by_asin, seller_search_query_performance
  from web_user;
revoke all on sequence seller_accounts_id_seq, seller_report_loads_id_seq from web_user;
revoke all on function seller_report_reject(text, text),
                       seller_report_table(text),
                       seller_report_argument_columns(text),
                       seller_report_sqp_view(text),
                       seller_report_check_source(text),
                       seller_report_lock_account(integer),
                       seller_report_check_rows(text, jsonb),
                       seller_report_check_range(date, date),
                       seller_report_sqp_period_end(text, date),
                       seller_report_period_rows(integer, text, text, date, date),
                       seller_report_write_period(integer, text, text, text, date, date, jsonb),
                       seller_report_keep_version(integer, text, text, date, date, bigint),
                       seller_report_open_load(integer, text, text, text, text, text, integer),
                       seller_report_needs_confirmation(text, text, boolean),
                       seller_report_save_status(text, text, text, text, boolean),
                       seller_report_save(integer, text, text, jsonb, boolean, boolean, text, text),
                       save_seller_sales_traffic_daily(integer, jsonb, text, boolean, boolean, text, text),
                       save_seller_sales_traffic_by_asin(integer, date, date, jsonb, text, boolean, boolean, text,
                                                         text),
                       save_seller_search_query_performance(integer, text, text, text, date, jsonb, text, boolean,
                                                            boolean, text, text),
                       upload_seller_sales_traffic_daily(integer, jsonb, boolean, boolean, text, text),
                       upload_seller_sales_traffic_by_asin(integer, date, date, jsonb, boolean, boolean, text, text),
                       upload_seller_search_query_performance(integer, text, text, text, date, jsonb, boolean,
                                                              boolean, text, text),
                       delete_seller_report_periods(integer, text, text, date, date, boolean, boolean, text),
                       revert_seller_report_load(bigint, boolean, text),
                       seller_account_for_ads_profile(text, text),
                       set_selling_partner_id(integer, text, text),
                       delete_seller_account(integer)
  from public, web_user;

-- Nobody writes these tables directly: every write goes through the functions, which run as their owner.
grant select on seller_accounts, seller_report_loads, seller_report_periods, seller_report_period_history,
                seller_sales_traffic_daily, seller_sales_traffic_by_asin, seller_search_query_performance
  to web_user, integ_worker;
grant execute on function upload_seller_sales_traffic_daily(integer, jsonb, boolean, boolean, text, text),
                          upload_seller_sales_traffic_by_asin(integer, date, date, jsonb, boolean, boolean, text,
                                                              text),
                          upload_seller_search_query_performance(integer, text, text, text, date, jsonb, boolean,
                                                                 boolean, text, text),
                          delete_seller_report_periods(integer, text, text, date, date, boolean, boolean, text),
                          revert_seller_report_load(bigint, boolean, text),
                          set_selling_partner_id(integer, text, text),
                          delete_seller_account(integer)
  to web_user;
grant execute on function save_seller_sales_traffic_daily(integer, jsonb, text, boolean, boolean, text, text),
                          save_seller_sales_traffic_by_asin(integer, date, date, jsonb, text, boolean, boolean, text,
                                                            text),
                          save_seller_search_query_performance(integer, text, text, text, date, jsonb, text, boolean,
                                                               boolean, text, text)
  to integ_worker;
grant execute on function seller_account_for_ads_profile(text, text) to web_user, integ_worker;

commit;

-- PostgREST caches the schema: without this the new tables and functions answer 404 until it restarts.
notify pgrst, 'reload schema';

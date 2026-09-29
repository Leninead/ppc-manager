-- 021 — Sponsored Brands search terms, for PPC Audit Pro.
--
-- Additive. Reporting v3's sbSearchTerm leaves out the SB campaigns of the old format (isMultiAdGroupsEnabled =
-- false), as its campaign reports do; SB's v2 keywords report split by query brings them. Both sources share the table
-- as the SB campaign days of 015 do: each rewrites only its own rows of the day, v2 keeps only the campaigns listed
-- with the old format, and v2's rows count once its history has loaded.

begin;

create table if not exists ads_sb_search_term_daily (
    profile_id       text   not null collate "C",
    report_date      date   not null,
    -- v3: sbSearchTerm. v2: the keywords report split by query, for the campaigns of the old format.
    source           text   not null default 'v3' collate "C" check (source in ('v3', 'v2')),
    campaign_id      text   not null collate "C",
    ad_group_id      text   not null default '' collate "C",
    keyword_id       text   not null default '' collate "C",
    search_term      text   not null collate "C",
    -- Empty on v2 rows: the read takes them from the SB keyword list.
    keyword_text     text   not null default '',
    match_type       text   not null default '',
    impressions      bigint not null default 0,
    clicks           bigint not null default 0,
    cost             numeric(14,4) not null default 0,
    -- 14 days, clicks or views: what Campaign Manager shows as Purchases / Sales.
    purchases        bigint not null default 0,
    sales            numeric(14,4) not null default 0,
    -- 14 days, clicks only: what compares with SP.
    purchases_clicks bigint not null default 0,
    sales_clicks     numeric(14,4) not null default 0,
    currency_code    text   not null default '',
    ingested_at      timestamptz not null default now(),
    primary key (profile_id, report_date, source, campaign_id, ad_group_id, keyword_id, search_term)
);
-- Every refresh rewrites whole days, so the default 20% dead-tuple threshold lags far behind.
alter table ads_sb_search_term_daily set (autovacuum_vacuum_scale_factor = 0.02,
                                          autovacuum_analyze_scale_factor = 0.01);


-- Rewrites one source's rows of the day: what Amazon did not send stops existing for that day, and the other source's
-- rows stay. Mirrors replace_sb_sd_campaign_day.
create or replace function replace_sb_search_term_day(p_profile_id text, p_day date, p_rows jsonb,
                                                      p_source text default 'v3')
returns integer
language plpgsql
set statement_timeout = '120s'
as $$
declare
    inserted_count integer;
begin
    if p_source not in ('v3', 'v2') then
        raise exception 'replace_sb_search_term_day: unknown source %', p_source;
    end if;
    -- A null or non-array payload would fall through to the delete and wipe the day.
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'replace_sb_search_term_day: p_rows must be a json array';
    end if;

    if jsonb_array_length(p_rows) = 0 then
        if exists (select 1 from ads_sb_search_term_daily
                    where profile_id = p_profile_id and report_date = p_day and source = p_source) then
            return -1;
        end if;
        return 0;
    end if;

    delete from ads_sb_search_term_daily
     where profile_id = p_profile_id and report_date = p_day and source = p_source;

    insert into ads_sb_search_term_daily (
        profile_id, report_date, source, campaign_id, ad_group_id, keyword_id, search_term, keyword_text,
        match_type, impressions, clicks, cost, purchases, sales, purchases_clicks, sales_clicks, currency_code
    )
    select p_profile_id, p_day, p_source, row_data.campaign_id, coalesce(row_data.ad_group_id, ''),
           coalesce(row_data.keyword_id, ''), row_data.search_term, coalesce(row_data.keyword_text, ''),
           coalesce(row_data.match_type, ''), coalesce(row_data.impressions, 0), coalesce(row_data.clicks, 0),
           coalesce(row_data.cost, 0), coalesce(row_data.purchases, 0), coalesce(row_data.sales, 0),
           coalesce(row_data.purchases_clicks, 0), coalesce(row_data.sales_clicks, 0),
           coalesce(row_data.currency_code, '')
      from jsonb_populate_recordset(null::ads_sb_search_term_daily, p_rows) as row_data
     -- v2 also brings the campaigns v3 reports: from it only the old-format ones enter, or their terms would count
     -- twice.
     where p_source = 'v3' or exists (
           select 1 from ads_sb_sd_campaign listed
            where listed.profile_id = p_profile_id and listed.ad_product = 'SB'
              and listed.campaign_id = row_data.campaign_id and listed.is_multi_ad_groups = false);

    get diagnostics inserted_count = row_count;
    return inserted_count;
end;
$$;


-- The SB search terms of the range, one row per campaign, ad group, keyword and term, with the campaign's name from
-- the SB list and, where the row lacks them (v2), the keyword's text and match type from the SB keyword list. As in
-- the SB campaign reads, v2's rows count only once its history has loaded: until then its days are partial.
create or replace function sb_search_terms_between(p_profile_id text, p_from date, p_to date)
returns table (
    campaign_id      text,
    campaign_name    text,
    ad_group_id      text,
    keyword_id       text,
    keyword_text     text,
    match_type       text,
    search_term      text,
    impressions      bigint,
    clicks           bigint,
    cost             numeric,
    purchases        bigint,
    sales            numeric,
    purchases_clicks bigint,
    sales_clicks     numeric,
    currency_code    text
)
language sql
stable
as $$
    with legacy as materialized (
        select exists (
            select 1 from integration_sync_jobs job
             where job.integration_slug = 'amazon_ads' and job.external_account_id = p_profile_id
               and job.job_kind = 'sb_legacy_search_terms' and job.status = 'completed'
               and job.trigger in ('backfill', 'retry')
        ) as done
    ),
    totals as (
        select daily.campaign_id, daily.ad_group_id, daily.keyword_id, daily.search_term,
               -- A keyword's text and match type never change, and v2's rows leave them empty.
               max(daily.keyword_text)             as keyword_text,
               max(daily.match_type)               as match_type,
               sum(daily.impressions)::bigint      as impressions,
               sum(daily.clicks)::bigint           as clicks,
               sum(daily.cost)                     as cost,
               sum(daily.purchases)::bigint        as purchases,
               sum(daily.sales)                    as sales,
               sum(daily.purchases_clicks)::bigint as purchases_clicks,
               sum(daily.sales_clicks)             as sales_clicks,
               max(daily.currency_code)            as currency_code
          from ads_sb_search_term_daily daily
          cross join legacy
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
           and (daily.source = 'v3' or legacy.done)
         group by daily.campaign_id, daily.ad_group_id, daily.keyword_id, daily.search_term
    )
    select totals.campaign_id, coalesce(campaign.name, ''), totals.ad_group_id, totals.keyword_id,
           coalesce(nullif(totals.keyword_text, ''), keyword.target_text, ''),
           coalesce(nullif(totals.match_type, ''), keyword.match_type, ''),
           totals.search_term, totals.impressions, totals.clicks, totals.cost, totals.purchases, totals.sales,
           totals.purchases_clicks, totals.sales_clicks, totals.currency_code
      from totals
      left join ads_sb_sd_campaign campaign
             on campaign.profile_id = p_profile_id and campaign.ad_product = 'SB'
            and campaign.campaign_id = totals.campaign_id
      left join ads_target keyword
             on keyword.profile_id = p_profile_id and keyword.ad_product = 'SB'
            and keyword.target_id = totals.keyword_id;
$$;


-- Revoke first: schema.sql gives web_user CRUD on every new table, and Postgres gives public EXECUTE on every new
-- function.
revoke all on ads_sb_search_term_daily from web_user;
revoke all on function replace_sb_search_term_day(text, date, jsonb, text),
                       sb_search_terms_between(text, date, date)
  from public, web_user;

grant select on ads_sb_search_term_daily to web_user;
grant execute on function sb_search_terms_between(text, date, date) to web_user;

grant select, insert, update, delete on ads_sb_search_term_daily to integ_worker;
grant execute on function replace_sb_search_term_day(text, date, jsonb, text) to integ_worker;

commit;

-- PostgREST caches the schema: without this the new table and functions answer 404 until it restarts.
notify pgrst, 'reload schema';

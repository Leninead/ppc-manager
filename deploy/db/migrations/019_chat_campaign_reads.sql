-- 019 — the chat's reads by campaign id, new-to-brand for SB and SD, and the SB and SD keywords and targets.
--
-- Additive for readers: the changed functions only gain columns, read by name. SD's campaign report starts asking
-- for new-to-brand, so the SD rows stored before carry an unknown value, not a zero.

begin;

-- SD's report never asked for new-to-brand: its zeros were never measured.
alter table ads_sb_sd_campaign_daily
    alter column new_to_brand_purchases drop not null,
    alter column new_to_brand_purchases drop default,
    alter column new_to_brand_sales drop not null,
    alter column new_to_brand_sales drop default;
update ads_sb_sd_campaign_daily set new_to_brand_purchases = null, new_to_brand_sales = null where ad_product = 'SD';


drop function if exists campaign_daily_totals(text, date, date, text);
create function campaign_daily_totals(p_profile_id text, p_from date, p_to date, p_campaign text default null)
returns table (
    report_date            date,
    ad_product             text,
    impressions            bigint,
    clicks                 bigint,
    cost                   numeric,
    purchases_7d           bigint,
    sales_7d               numeric,
    purchases_14d          bigint,
    sales_14d              numeric,
    purchases              bigint,
    sales                  numeric,
    purchases_clicks       bigint,
    sales_clicks           numeric,
    currency_code          text,
    campaign_names         text[],
    new_to_brand_purchases bigint,
    new_to_brand_sales     numeric
)
language sql
stable
as $$
    with legacy as materialized (
        select sb_legacy_history_done(p_profile_id) as done
    ),
    activity as (
        select daily.report_date, 'SP'::text as ad_product, daily.impressions, daily.clicks, daily.cost,
               daily.purchases_7d, daily.sales_7d, daily.purchases_14d, daily.sales_14d,
               0::bigint as purchases, 0::numeric as sales, 0::bigint as purchases_clicks,
               0::numeric as sales_clicks, null::bigint as new_to_brand_purchases,
               null::numeric as new_to_brand_sales, daily.currency_code, campaign.name
          from ads_campaign_daily daily
          left join ads_campaign campaign
                 on campaign.profile_id = daily.profile_id and campaign.campaign_id = daily.campaign_id
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
        union all
        select daily.report_date, daily.ad_product, daily.impressions, daily.clicks, daily.cost,
               0::bigint, 0::numeric, 0::bigint, 0::numeric,
               daily.purchases, daily.sales, daily.purchases_clicks, daily.sales_clicks,
               daily.new_to_brand_purchases, daily.new_to_brand_sales, daily.currency_code, campaign.name
          from ads_sb_sd_campaign_daily daily
          cross join legacy
          left join ads_sb_sd_campaign campaign
                 on campaign.profile_id = daily.profile_id and campaign.ad_product = daily.ad_product
                and campaign.campaign_id = daily.campaign_id
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
           and (daily.source = 'v3' or legacy.done)
    )
    select activity.report_date, activity.ad_product,
           sum(activity.impressions)::bigint, sum(activity.clicks)::bigint, sum(activity.cost),
           sum(activity.purchases_7d)::bigint, sum(activity.sales_7d),
           sum(activity.purchases_14d)::bigint, sum(activity.sales_14d),
           sum(activity.purchases)::bigint, sum(activity.sales),
           sum(activity.purchases_clicks)::bigint, sum(activity.sales_clicks),
           max(activity.currency_code),
           case when p_campaign is null then null
                else array_agg(distinct activity.name order by activity.name)
                         filter (where activity.name is not null) end,
           -- One unmeasured row makes the day's new-to-brand unknown.
           case when bool_and(activity.new_to_brand_purchases is not null)
                then sum(activity.new_to_brand_purchases)::bigint end,
           case when bool_and(activity.new_to_brand_sales is not null)
                then sum(activity.new_to_brand_sales) end
      from activity
     where p_campaign is null or strpos(lower(coalesce(activity.name, '')), lower(p_campaign)) > 0
     group by activity.report_date, activity.ad_product
     order by activity.report_date, activity.ad_product;
$$;


drop function if exists campaign_window_totals(text, date, date);
create function campaign_window_totals(p_profile_id text, p_from date, p_to date)
returns table (
    ad_product             text,
    campaign_id            text,
    campaign_name          text,
    portfolio_id           text,
    portfolio_name         text,
    impressions            bigint,
    clicks                 bigint,
    cost                   numeric,
    purchases_7d           bigint,
    sales_7d               numeric,
    purchases_14d          bigint,
    sales_14d              numeric,
    purchases              bigint,
    sales                  numeric,
    purchases_clicks       bigint,
    sales_clicks           numeric,
    currency_code          text,
    new_to_brand_purchases bigint,
    new_to_brand_sales     numeric
)
language sql
stable
as $$
    with legacy as materialized (
        select sb_legacy_history_done(p_profile_id) as done
    ),
    sp as (
        select daily.campaign_id,
               sum(daily.impressions)::bigint as impressions, sum(daily.clicks)::bigint as clicks,
               sum(daily.cost) as cost, sum(daily.purchases_7d)::bigint as purchases_7d,
               sum(daily.sales_7d) as sales_7d, sum(daily.purchases_14d)::bigint as purchases_14d,
               sum(daily.sales_14d) as sales_14d, max(daily.currency_code) as currency_code
          from ads_campaign_daily daily
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
         group by daily.campaign_id
    ),
    others as (
        select daily.ad_product, daily.campaign_id,
               sum(daily.impressions)::bigint as impressions, sum(daily.clicks)::bigint as clicks,
               sum(daily.cost) as cost, sum(daily.purchases)::bigint as purchases, sum(daily.sales) as sales,
               sum(daily.purchases_clicks)::bigint as purchases_clicks, sum(daily.sales_clicks) as sales_clicks,
               max(daily.currency_code) as currency_code,
               case when bool_and(daily.new_to_brand_purchases is not null)
                    then sum(daily.new_to_brand_purchases)::bigint end as new_to_brand_purchases,
               case when bool_and(daily.new_to_brand_sales is not null)
                    then sum(daily.new_to_brand_sales) end as new_to_brand_sales
          from ads_sb_sd_campaign_daily daily
          cross join legacy
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
           and (daily.source = 'v3' or legacy.done)
         group by daily.ad_product, daily.campaign_id
    )
    select 'SP'::text, sp.campaign_id, coalesce(campaign.name, ''), coalesce(campaign.portfolio_id, ''),
           coalesce(portfolio.name, ''), sp.impressions, sp.clicks, sp.cost, sp.purchases_7d, sp.sales_7d,
           sp.purchases_14d, sp.sales_14d, 0::bigint, 0::numeric, 0::bigint, 0::numeric, sp.currency_code,
           null::bigint, null::numeric
      from sp
      left join ads_campaign campaign on campaign.profile_id = p_profile_id and campaign.campaign_id = sp.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id and portfolio.portfolio_id = campaign.portfolio_id
    union all
    select others.ad_product, others.campaign_id, coalesce(campaign.name, ''), coalesce(campaign.portfolio_id, ''),
           coalesce(portfolio.name, ''), others.impressions, others.clicks, others.cost, 0::bigint, 0::numeric,
           0::bigint, 0::numeric, others.purchases, others.sales, others.purchases_clicks, others.sales_clicks,
           others.currency_code, others.new_to_brand_purchases, others.new_to_brand_sales
      from others
      left join ads_sb_sd_campaign campaign
             on campaign.profile_id = p_profile_id and campaign.ad_product = others.ad_product
            and campaign.campaign_id = others.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id and portfolio.portfolio_id = campaign.portfolio_id;
$$;


drop function if exists product_campaigns_between(text, date, date);
create function product_campaigns_between(p_profile_id text, p_from date, p_to date)
returns table (
    ad_product             text,
    campaign_id            text,
    name                   text,
    state                  text,
    start_date             date,
    budget_amount          numeric,
    budget_type            text,
    cost_type              text,
    portfolio_id           text,
    portfolio_name         text,
    is_multi_ad_groups     boolean,
    bid_strategy           text,
    metrics_known          boolean,
    impressions            bigint,
    clicks                 bigint,
    cost                   numeric,
    purchases              bigint,
    sales                  numeric,
    purchases_clicks       bigint,
    sales_clicks           numeric,
    viewable_impressions   bigint,
    currency_code          text,
    new_to_brand_purchases bigint,
    new_to_brand_sales     numeric
)
language sql
stable
as $$
    with latest as (
        select listed.ad_product, max(listed.seen_at) as seen_at
          from ads_sb_sd_campaign listed
         where listed.profile_id = p_profile_id
         group by listed.ad_product
    ),
    totals as (
        select daily.ad_product, daily.campaign_id,
               sum(daily.impressions)::bigint          as impressions,
               sum(daily.clicks)::bigint               as clicks,
               sum(daily.cost)                         as cost,
               sum(daily.purchases)::bigint            as purchases,
               sum(daily.sales)                        as sales,
               sum(daily.purchases_clicks)::bigint     as purchases_clicks,
               sum(daily.sales_clicks)                 as sales_clicks,
               sum(daily.viewable_impressions)::bigint as viewable_impressions,
               max(daily.currency_code)                as currency_code,
               sum(daily.new_to_brand_purchases)::bigint as new_to_brand_purchases,
               sum(daily.new_to_brand_sales)           as new_to_brand_sales,
               bool_and(daily.new_to_brand_purchases is not null and daily.new_to_brand_sales is not null)
                                                       as new_to_brand_known
          from ads_sb_sd_campaign_daily daily
         where daily.profile_id = p_profile_id
           and daily.report_date between p_from and p_to
         group by daily.ad_product, daily.campaign_id
    ),
    legacy_history as materialized (
        select sb_legacy_history_done(p_profile_id) as done
    )
    select campaign.ad_product, campaign.campaign_id, campaign.name, campaign.state, campaign.start_date,
           campaign.budget_amount, campaign.budget_type, campaign.cost_type, campaign.portfolio_id,
           coalesce(portfolio.name, '') as portfolio_name, campaign.is_multi_ad_groups, campaign.bid_strategy,
           (campaign.ad_product <> 'SB' or coalesce(campaign.is_multi_ad_groups, true) or legacy_history.done)
               as metrics_known,
           coalesce(totals.impressions, 0)::bigint          as impressions,
           coalesce(totals.clicks, 0)::bigint               as clicks,
           coalesce(totals.cost, 0)                         as cost,
           coalesce(totals.purchases, 0)::bigint            as purchases,
           coalesce(totals.sales, 0)                        as sales,
           coalesce(totals.purchases_clicks, 0)::bigint     as purchases_clicks,
           coalesce(totals.sales_clicks, 0)                 as sales_clicks,
           coalesce(totals.viewable_impressions, 0)::bigint as viewable_impressions,
           coalesce(totals.currency_code, '')               as currency_code,
           -- A campaign without a day in the range had no new-to-brand sale: zero, not unknown.
           case when coalesce(totals.new_to_brand_known, true)
                then coalesce(totals.new_to_brand_purchases, 0)::bigint end as new_to_brand_purchases,
           case when coalesce(totals.new_to_brand_known, true)
                then coalesce(totals.new_to_brand_sales, 0) end as new_to_brand_sales
      from ads_sb_sd_campaign campaign
      join latest on latest.ad_product = campaign.ad_product and latest.seen_at = campaign.seen_at
      cross join legacy_history
      left join totals on totals.ad_product = campaign.ad_product and totals.campaign_id = campaign.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id
            and portfolio.portfolio_id = campaign.portfolio_id
     where campaign.profile_id = p_profile_id
     order by campaign.ad_product, campaign.name;
$$;


-- Every campaign of the three products in its last listing: what a campaign name or id is resolved against.
create function campaign_catalog(p_profile_id text)
returns table (
    ad_product     text,
    campaign_id    text,
    name           text,
    state          text,
    portfolio_id   text,
    portfolio_name text,
    budget_amount  numeric,
    budget_type    text
)
language sql
stable
as $$
    with sb_sd_latest as (
        select listed.ad_product, max(listed.seen_at) as seen_at
          from ads_sb_sd_campaign listed
         where listed.profile_id = p_profile_id
         group by listed.ad_product
    ),
    listed as (
        select 'SP'::text as ad_product, campaign.campaign_id, campaign.name, campaign.state, campaign.portfolio_id,
               campaign.budget_amount, campaign.budget_type
          from ads_campaign campaign
         where campaign.profile_id = p_profile_id
           and campaign.seen_at = (select max(latest.seen_at) from ads_campaign latest
                                    where latest.profile_id = p_profile_id)
        union all
        select campaign.ad_product, campaign.campaign_id, campaign.name, campaign.state, campaign.portfolio_id,
               campaign.budget_amount, campaign.budget_type
          from ads_sb_sd_campaign campaign
          join sb_sd_latest latest on latest.ad_product = campaign.ad_product and latest.seen_at = campaign.seen_at
         where campaign.profile_id = p_profile_id
    )
    select listed.ad_product, listed.campaign_id, listed.name, upper(listed.state), listed.portfolio_id,
           coalesce(portfolio.name, ''), listed.budget_amount, listed.budget_type
      from listed
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id and portfolio.portfolio_id = listed.portfolio_id;
$$;


-- One row per campaign and day for the campaigns asked for by id, so a name shared by several never merges them.
create function campaign_daily_totals_by_campaign(p_profile_id text, p_from date, p_to date,
                                                  p_campaign_ids text[])
returns table (
    report_date            date,
    ad_product             text,
    campaign_id            text,
    impressions            bigint,
    clicks                 bigint,
    cost                   numeric,
    purchases_7d           bigint,
    sales_7d               numeric,
    purchases_14d          bigint,
    sales_14d              numeric,
    purchases              bigint,
    sales                  numeric,
    purchases_clicks       bigint,
    sales_clicks           numeric,
    new_to_brand_purchases bigint,
    new_to_brand_sales     numeric,
    currency_code          text
)
language sql
stable
as $$
    with legacy as materialized (
        select sb_legacy_history_done(p_profile_id) as done
    )
    select daily.report_date, 'SP'::text, daily.campaign_id, daily.impressions, daily.clicks, daily.cost,
           daily.purchases_7d, daily.sales_7d, daily.purchases_14d, daily.sales_14d,
           0::bigint, 0::numeric, 0::bigint, 0::numeric, null::bigint, null::numeric, daily.currency_code
      from ads_campaign_daily daily
     where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
       and daily.campaign_id = any (p_campaign_ids)
    union all
    select daily.report_date, daily.ad_product, daily.campaign_id, daily.impressions, daily.clicks, daily.cost,
           0::bigint, 0::numeric, 0::bigint, 0::numeric, daily.purchases, daily.sales, daily.purchases_clicks,
           daily.sales_clicks, daily.new_to_brand_purchases, daily.new_to_brand_sales, daily.currency_code
      from ads_sb_sd_campaign_daily daily
      cross join legacy
     where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
       and daily.campaign_id = any (p_campaign_ids)
       and (daily.source = 'v3' or legacy.done)
     order by 1, 2, 3;
$$;


-- The same from the search terms, only Sponsored Products.
create function ads_daily_totals_by_campaign(p_profile_id text, p_from date, p_to date, p_campaign_ids text[])
returns table (
    report_date   date,
    campaign_id   text,
    impressions   bigint,
    clicks        bigint,
    cost          numeric,
    purchases_7d  bigint,
    sales_7d      numeric,
    purchases_14d bigint,
    sales_14d     numeric,
    currency_code text
)
language sql
stable
as $$
    select daily.report_date, daily.campaign_id,
           sum(daily.impressions)::bigint, sum(daily.clicks)::bigint, sum(daily.cost),
           sum(daily.purchases_7d)::bigint, sum(daily.sales_7d),
           sum(daily.purchases_14d)::bigint, sum(daily.sales_14d),
           max(daily.currency_code)
      from ads_search_term_daily daily
     where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
       and daily.campaign_id = any (p_campaign_ids)
     group by daily.report_date, daily.campaign_id
     order by daily.report_date, daily.campaign_id;
$$;


-- The keywords and targets of the SB or SD campaigns in their last listing, with their effective bid and the
-- range's metrics, in the columns the SP structure gives its targets. cost_type says whether the bid is per click or
-- per thousand viewable impressions (VCPM).
create function sb_sd_targets_between(p_profile_id text, p_from date, p_to date, p_ad_product text,
                                      p_campaign_ids text[] default null)
returns table (
    entity              text,
    campaign_id         text,
    ad_group_id         text,
    entity_id           text,
    campaign_name       text,
    campaign_state      text,
    cost_type           text,
    ad_group_name       text,
    state               text,
    target_kind         text,
    target_text         text,
    match_type          text,
    default_bid         numeric,
    own_bid             numeric,
    bid                 numeric,
    impressions         bigint,
    clicks              bigint,
    cost                numeric,
    purchases           bigint,
    sales               numeric,
    purchases_clicks    bigint,
    sales_clicks        numeric,
    top_of_search_share numeric,
    metrics_known       boolean,
    currency_code       text,
    listed_at           timestamptz
)
language sql
stable
as $$
    with latest_targets as (
        select max(listed.seen_at) as seen_at
          from ads_target listed
         where listed.profile_id = p_profile_id and listed.ad_product = p_ad_product
    ),
    latest_campaigns as (
        select max(listed.seen_at) as seen_at
          from ads_sb_sd_campaign listed
         where listed.profile_id = p_profile_id and listed.ad_product = p_ad_product
    ),
    campaigns as (
        select campaign.campaign_id, campaign.name, upper(campaign.state) as state, campaign.cost_type,
               -- The old-format SB campaigns only report by campaign: their targets have no metrics.
               not (campaign.ad_product = 'SB' and not coalesce(campaign.is_multi_ad_groups, true)) as reported
          from ads_sb_sd_campaign campaign
          join latest_campaigns on latest_campaigns.seen_at = campaign.seen_at
         where campaign.profile_id = p_profile_id and campaign.ad_product = p_ad_product
    ),
    coverage as (
        select exists (select 1 from ads_target_daily daily
                        where daily.profile_id = p_profile_id and daily.ad_product = p_ad_product
                          and daily.report_date between p_from and p_to) as known,
               coalesce((select max(daily.currency_code) from ads_target_daily daily
                          where daily.profile_id = p_profile_id and daily.ad_product = p_ad_product
                            and daily.report_date between p_from and p_to), '') as currency_code
    ),
    totals as (
        select daily.target_id,
               sum(daily.impressions)::bigint      as impressions,
               sum(daily.clicks)::bigint           as clicks,
               sum(daily.cost)                     as cost,
               sum(daily.purchases)::bigint        as purchases,
               sum(daily.sales)                    as sales,
               sum(daily.purchases_clicks)::bigint as purchases_clicks,
               sum(daily.sales_clicks)             as sales_clicks,
               -- Weighted by impressions, as campaigns_between weighs a campaign's share.
               round(sum(daily.top_of_search_is * daily.impressions)
                         filter (where daily.top_of_search_is is not null and daily.impressions > 0)
                     / nullif(sum(daily.impressions)
                         filter (where daily.top_of_search_is is not null and daily.impressions > 0), 0),
                     2)                            as top_of_search_share
          from ads_target_daily daily
         where daily.profile_id = p_profile_id and daily.ad_product = p_ad_product
           and daily.report_date between p_from and p_to
         group by daily.target_id
    )
    select case when target.target_kind = 'keyword' then 'keyword' else 'product_targeting' end,
           target.campaign_id, target.ad_group_id, target.target_id,
           coalesce(campaigns.name, ''), coalesce(campaigns.state, ''), coalesce(campaigns.cost_type, ''),
           target.ad_group_name, upper(target.state),
           target.target_kind, target.target_text, target.match_type,
           target.default_bid, target.own_bid, target.bid,
           coalesce(totals.impressions, 0)::bigint, coalesce(totals.clicks, 0)::bigint, coalesce(totals.cost, 0),
           coalesce(totals.purchases, 0)::bigint, coalesce(totals.sales, 0),
           coalesce(totals.purchases_clicks, 0)::bigint, coalesce(totals.sales_clicks, 0),
           totals.top_of_search_share,
           coverage.known and coalesce(campaigns.reported, true),
           coverage.currency_code, target.seen_at
      from ads_target_bid target
      join latest_targets on latest_targets.seen_at = target.seen_at
      cross join coverage
      left join campaigns on campaigns.campaign_id = target.campaign_id
      left join totals on totals.target_id = target.target_id
     where target.profile_id = p_profile_id and target.ad_product = p_ad_product
       and (p_campaign_ids is null or target.campaign_id = any (p_campaign_ids));
$$;


-- Each target's top-of-search impression share over the range, weighted by impressions.
create function target_top_of_search_between(p_profile_id text, p_from date, p_to date, p_ad_product text)
returns table (
    target_id           text,
    top_of_search_share numeric
)
language sql
stable
as $$
    select daily.target_id,
           round(sum(daily.top_of_search_is * daily.impressions)
                     filter (where daily.top_of_search_is is not null and daily.impressions > 0)
                 / nullif(sum(daily.impressions)
                     filter (where daily.top_of_search_is is not null and daily.impressions > 0), 0),
                 2)
      from ads_target_daily daily
     where daily.profile_id = p_profile_id and daily.ad_product = p_ad_product
       and daily.report_date between p_from and p_to
     group by daily.target_id
    having sum(daily.impressions) filter (where daily.top_of_search_is is not null and daily.impressions > 0) > 0;
$$;


-- Revoke first: Postgres gives EXECUTE to public on every new function.
revoke all on function campaign_daily_totals(text, date, date, text),
                       campaign_window_totals(text, date, date),
                       product_campaigns_between(text, date, date),
                       campaign_catalog(text),
                       campaign_daily_totals_by_campaign(text, date, date, text[]),
                       ads_daily_totals_by_campaign(text, date, date, text[]),
                       sb_sd_targets_between(text, date, date, text, text[]),
                       target_top_of_search_between(text, date, date, text)
  from public, web_user;

grant execute on function campaign_daily_totals(text, date, date, text),
                          campaign_window_totals(text, date, date),
                          product_campaigns_between(text, date, date),
                          campaign_catalog(text),
                          campaign_daily_totals_by_campaign(text, date, date, text[]),
                          ads_daily_totals_by_campaign(text, date, date, text[]),
                          sb_sd_targets_between(text, date, date, text, text[]),
                          target_top_of_search_between(text, date, date, text)
  to web_user;

-- The Bulk Campañas analysis worker reads the SB and SD campaigns, as 015 granted it.
grant execute on function product_campaigns_between(text, date, date) to ai_worker;

commit;

-- PostgREST caches the schema: without this the new functions answer 404 until it restarts.
notify pgrst, 'reload schema';

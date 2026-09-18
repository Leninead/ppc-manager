-- The chat can only draw how an account or a campaign is doing over time if something hands it
-- the days. ads_search_term_daily already keeps one row per day, but search_terms_between sums
-- the whole window, so every series the model saw had a single point.
--
-- This sums by day in the database: the answer is at most one row per day of the window, instead
-- of the thousands of search-term rows the caller would otherwise download to add up itself.
-- Both attribution windows travel so the caller picks the one the account's console uses, the
-- same way the Search Term Report does.

create or replace function ads_daily_totals(p_profile_id text, p_from date, p_to date,
                                            p_campaign text default null)
returns table (
    report_date    date,
    impressions    bigint,
    clicks         bigint,
    cost           numeric,
    purchases_7d   bigint,
    sales_7d       numeric,
    purchases_14d  bigint,
    sales_14d      numeric,
    currency_code  text,
    campaign_names text[]
)
language sql
stable
as $$
    select daily.report_date,
           sum(daily.impressions)::bigint,
           sum(daily.clicks)::bigint,
           sum(daily.cost),
           sum(daily.purchases_7d)::bigint,
           sum(daily.sales_7d),
           sum(daily.purchases_14d)::bigint,
           sum(daily.sales_14d),
           max(daily.currency_code),
           -- Only when filtering: the caller has to say which campaigns a name fragment matched.
           case when p_campaign is null then null
                else array_agg(distinct daily.campaign_name order by daily.campaign_name) end
      from ads_search_term_daily daily
     where daily.profile_id = p_profile_id
       and daily.report_date between p_from and p_to
       -- strpos, not ilike: campaign names carry '_' and '%', which ilike would read as wildcards.
       and (p_campaign is null or strpos(lower(daily.campaign_name), lower(p_campaign)) > 0)
     group by daily.report_date
     order by daily.report_date;
$$;

revoke all on function ads_daily_totals(text, date, date, text) from public, web_user;
grant execute on function ads_daily_totals(text, date, date, text) to web_user;

-- PostgREST cachea el esquema: sin esto la función nueva no existe para él hasta un reinicio.
notify pgrst, 'reload schema';

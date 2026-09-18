-- 014 — la capa de IA de Bulk Campañas (M6) y las señales que la alimentan.
--
-- Tres cosas, en este orden:
--
-- 1. ads_campaign_daily guarda el presupuesto y el top-of-search impression share de cada día,
--    que el reporte spCampaigns ya trae. Medido contra la API real (timeUnit DAILY): el presupuesto
--    viene en todas las filas y el share en porcentaje, de 0 a 100, nulo en las filas sin
--    elegibilidad. Con el presupuesto de cada día, y no con el de la foto de hoy, "limitada por
--    presupuesto" no se equivoca cuando alguien lo cambió en el medio del período.
--
-- 2. campaigns_between devuelve además, por campaña: cuántos días del rango gastó al menos el 95%
--    de su presupuesto de ese día, cuántos días tuvo impresiones, y el share ponderado por
--    impresiones. Los días sincronizados antes de esta migración no tienen presupuesto propio y
--    usan el de la foto de la campaña; el refresco diario reescribe los 65 días, así que en una
--    noche no queda ninguno.
--
-- 3. bulk_campaigns entra en la lista de módulos con análisis guardado, y request_ai_analysis valida
--    su ventana contra la última sincronización de campañas completada: esa sincronización no
--    escribe ads_profile_sync y puede ir un día adelante o atrás de la del STR.

begin;

alter table ads_campaign_daily
    add column if not exists budget_amount    numeric(14,4),
    add column if not exists top_of_search_is numeric(7,4);

comment on column ads_campaign_daily.budget_amount is
    'Presupuesto de la campaña ese día (campaignBudgetAmount del reporte). Nulo en días sincronizados antes de la 014.';
comment on column ads_campaign_daily.top_of_search_is is
    'Top-of-search impression share del día, en porcentaje 0-100. Nulo cuando Amazon no lo informa.';


create or replace function replace_campaign_day(p_profile_id text, p_day date, p_rows jsonb)
returns integer
language plpgsql
set statement_timeout = '120s'
as $$
declare
    inserted_count integer;
begin
    -- Un payload nulo o que no sea array caería en el delete y borraría el día.
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'replace_campaign_day: p_rows must be a json array';
    end if;

    if jsonb_array_length(p_rows) = 0 then
        if exists (select 1 from ads_campaign_daily
                    where profile_id = p_profile_id and report_date = p_day) then
            return -1;
        end if;
        return 0;
    end if;

    delete from ads_campaign_daily
     where profile_id = p_profile_id and report_date = p_day;

    insert into ads_campaign_daily (
        profile_id, report_date, campaign_id, impressions, clicks, cost,
        purchases_7d, sales_7d, purchases_14d, sales_14d, currency_code,
        budget_amount, top_of_search_is
    )
    select p_profile_id, p_day, row_data.campaign_id, row_data.impressions, row_data.clicks,
           row_data.cost, row_data.purchases_7d, row_data.sales_7d, row_data.purchases_14d,
           row_data.sales_14d, row_data.currency_code, row_data.budget_amount, row_data.top_of_search_is
      from jsonb_populate_recordset(null::ads_campaign_daily, p_rows) as row_data;

    get diagnostics inserted_count = row_count;
    return inserted_count;
end;
$$;


-- Cambian las columnas que devuelve, así que no alcanza con create or replace.
drop function if exists campaigns_between(text, date, date);

create function campaigns_between(p_profile_id text, p_from date, p_to date)
returns table (
    campaign_id           text,
    name                  text,
    state                 text,
    targeting_type        text,
    start_date            date,
    budget_amount         numeric,
    budget_type           text,
    bidding_strategy      text,
    portfolio_id          text,
    portfolio_name        text,
    impressions           bigint,
    clicks                bigint,
    cost                  numeric,
    purchases_7d          bigint,
    sales_7d              numeric,
    purchases_14d         bigint,
    sales_14d             numeric,
    currency_code         text,
    budget_capped_days    integer,
    days_with_impressions integer,
    top_of_search_is      numeric
)
language sql
stable
as $$
    with totals as (
        select daily.campaign_id,
               sum(daily.impressions)::bigint   as impressions,
               sum(daily.clicks)::bigint        as clicks,
               sum(daily.cost)                  as cost,
               sum(daily.purchases_7d)::bigint  as purchases_7d,
               sum(daily.sales_7d)              as sales_7d,
               sum(daily.purchases_14d)::bigint as purchases_14d,
               sum(daily.sales_14d)             as sales_14d,
               max(daily.currency_code)         as currency_code,
               -- El 95% es el umbral de "limitada por presupuesto"; cuántos días hacen falta lo decide
               -- core/amazon_ads/campaign_analyzer.py.
               count(*) filter (
                   where coalesce(daily.budget_amount, campaign.budget_amount) > 0
                     and daily.cost >= 0.95 * coalesce(daily.budget_amount, campaign.budget_amount)
               )::integer                       as budget_capped_days,
               count(*) filter (where daily.impressions > 0)::integer as days_with_impressions,
               round(sum(daily.top_of_search_is * daily.impressions)
                         filter (where daily.top_of_search_is is not null and daily.impressions > 0)
                     / nullif(sum(daily.impressions)
                         filter (where daily.top_of_search_is is not null and daily.impressions > 0), 0),
                     2)                         as top_of_search_is
          from ads_campaign_daily daily
          left join ads_campaign campaign
                 on campaign.profile_id = daily.profile_id and campaign.campaign_id = daily.campaign_id
         where daily.profile_id = p_profile_id
           and daily.report_date between p_from and p_to
         group by daily.campaign_id
    )
    select campaign.campaign_id, campaign.name, campaign.state, campaign.targeting_type,
           campaign.start_date, campaign.budget_amount, campaign.budget_type,
           campaign.bidding_strategy, campaign.portfolio_id,
           coalesce(portfolio.name, '') as portfolio_name,
           coalesce(totals.impressions, 0)::bigint   as impressions,
           coalesce(totals.clicks, 0)::bigint        as clicks,
           coalesce(totals.cost, 0)                  as cost,
           coalesce(totals.purchases_7d, 0)::bigint  as purchases_7d,
           coalesce(totals.sales_7d, 0)              as sales_7d,
           coalesce(totals.purchases_14d, 0)::bigint as purchases_14d,
           coalesce(totals.sales_14d, 0)             as sales_14d,
           coalesce(totals.currency_code, '')        as currency_code,
           coalesce(totals.budget_capped_days, 0)    as budget_capped_days,
           coalesce(totals.days_with_impressions, 0) as days_with_impressions,
           totals.top_of_search_is
      from ads_campaign campaign
      left join totals on totals.campaign_id = campaign.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id
            and portfolio.portfolio_id = campaign.portfolio_id
     where campaign.profile_id = p_profile_id
     order by campaign.name;
$$;


create or replace function ai_analysis_module_allowed(p_module text)
returns boolean
language sql
immutable
as $$
    select p_module in ('str', 'bid_optimizer', 'bulk_campaigns');
$$;


-- Igual que la versión de la 011, salvo de dónde sale la cobertura contra la que se valida la ventana.
create or replace function request_ai_analysis(p_module text, p_subject_id text, p_window_start date,
                                               p_window_end date, p_lang text, p_params jsonb,
                                               p_input_digest text, p_requested_by text)
returns table (job_id bigint, created boolean, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
    profile        ads_profile_sync%rowtype;
    coverage_from  date;
    coverage_to    date;
    existing_id    bigint;
    local_today    date;
    new_job_id     bigint;
begin
    if not ai_analysis_module_allowed(p_module) or p_lang not in ('es','en') or jsonb_typeof(p_params) <> 'object'
       or coalesce(p_input_digest, '') = '' then
        return query select null::bigint, false, 'invalid_request'::text;
        return;
    end if;

    -- The row lock serializes two people pressing the button for the same account.
    select * into profile from ads_profile_sync where profile_id = p_subject_id for update;
    if not found or profile.status <> 'active' then
        return query select null::bigint, false, 'profile_unavailable'::text;
        return;
    end if;

    -- Cada módulo se analiza sobre lo que trajo su propia sincronización.
    if p_module = 'bulk_campaigns' then
        select campaign_job.window_start, campaign_job.window_end
          into coverage_from, coverage_to
          from integration_sync_jobs campaign_job
         where campaign_job.job_kind = 'sp_campaigns'
           and campaign_job.external_account_id = p_subject_id
           and campaign_job.status = 'completed'
         order by campaign_job.finished_at desc nulls last, campaign_job.id desc
         limit 1;
    else
        coverage_from := profile.data_from;
        coverage_to := profile.data_through;
    end if;
    if coverage_to is null then
        return query select null::bigint, false, 'profile_unavailable'::text;
        return;
    end if;
    if p_window_end < p_window_start or p_window_end > coverage_to
       or p_window_start < coalesce(coverage_from, coverage_to - 59)
       or p_window_end - p_window_start > 59 then
        return query select null::bigint, false, 'invalid_window'::text;
        return;
    end if;

    select analysis.job_id into existing_id
      from ai_analyses analysis
     where analysis.module = p_module and analysis.subject_id = p_subject_id
       and analysis.input_digest = p_input_digest and analysis.status = 'done'
     limit 1;
    if found then
        return query select existing_id, false, 'already_done'::text;
        return;
    end if;

    select open_job.id into existing_id
      from integration_sync_jobs open_job
     where open_job.job_kind = 'ai_' || p_module || '_analysis'
       and open_job.external_account_id = p_subject_id
       and open_job.params->>'input_digest' = p_input_digest
       and open_job.status in ('pending','running','retrying')
     order by open_job.created_at desc
     limit 1;
    if existing_id is not null then
        return query select existing_id, false, 'already_running'::text;
        return;
    end if;

    local_today := (now() at time zone coalesce(
        nullif(profile.timezone, ''),
        case profile.region when 'EU' then 'Europe/London' when 'FE' then 'Asia/Tokyo'
                            else 'America/Los_Angeles' end
    ))::date;

    insert into integration_sync_jobs (
        integration_slug, job_kind, trigger, account_id, connection_id, external_account_id,
        cliente, account_name, marketplace, region, window_start, window_end, local_day,
        max_attempts, deadline_at, requested_by, params
    ) values (
        'amazon_ads', 'ai_' || p_module || '_analysis', 'manual', profile.account_id, profile.connection_id,
        profile.profile_id, profile.cliente, profile.account_name, profile.country_code,
        profile.region, p_window_start, p_window_end, local_today,
        3, now() + interval '6 hours', coalesce(nullif(p_requested_by, ''), 'app'),
        jsonb_build_object('module', p_module, 'lang', p_lang, 'params', p_params,
                           'input_digest', p_input_digest)
    )
    returning id into new_job_id;

    return query select new_job_id, true, 'created'::text;
end;
$$;


-- La función nueva nace con EXECUTE para public: revocar primero, como en la 013.
revoke all on function campaigns_between(text, date, date) from public, web_user;
grant execute on function campaigns_between(text, date, date) to web_user, ai_worker;
-- El worker de análisis lee las campañas para armar el payload de M6; campaigns_between corre
-- con los permisos de quien la llama.
grant select on ads_campaign, ads_campaign_daily to ai_worker;

commit;

-- PostgREST cachea el esquema: sin esto, campaigns_between sigue contestando con las columnas viejas.
notify pgrst, 'reload schema';

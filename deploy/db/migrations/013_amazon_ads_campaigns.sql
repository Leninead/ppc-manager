-- 013 — grano de campaña de Amazon Ads (entidades + métricas diarias).
--
-- ads_campaign es la foto de las entidades: el universo completo de campañas del
-- perfil, incluidas las que no tuvieron actividad. ads_campaign_daily son las
-- métricas del report spCampaigns por día. La separación no es cosmética: el
-- report sólo devuelve campañas con actividad en el rango pedido (medido contra
-- la API real: 276 campañas en la cuenta, 46 en el report de una semana), así que
-- el universo tiene que salir de la entidad o las campañas sin impresiones
-- desaparecen — y con ellas el diagnóstico de campañas fantasma.
--
-- Por eso campaigns_between arranca en ads_campaign y trae las métricas con un
-- left join: la regla vive en el SQL y ningún caller puede saltearla.

begin;

create table if not exists ads_campaign (
    profile_id       text not null collate "C",
    campaign_id      text not null collate "C",
    name             text not null default '',
    state            text not null default '',
    targeting_type   text not null default '',
    start_date       date,
    end_date         date,
    budget_amount    numeric(14,4),
    budget_type      text not null default '',
    bidding_strategy text not null default '',
    portfolio_id     text not null default '',
    seen_at          timestamptz not null default now(),
    primary key (profile_id, campaign_id)
);


create table if not exists ads_campaign_daily (
    profile_id    text   not null collate "C",
    report_date   date   not null,
    campaign_id   text   not null collate "C",
    impressions   bigint not null default 0,
    clicks        bigint not null default 0,
    cost          numeric(14,4) not null default 0,
    purchases_7d  bigint not null default 0,
    sales_7d      numeric(14,4) not null default 0,
    purchases_14d bigint not null default 0,
    sales_14d     numeric(14,4) not null default 0,
    currency_code text   not null default '',
    ingested_at   timestamptz not null default now(),
    primary key (profile_id, report_date, campaign_id)
);
-- Cada refresco reescribe días enteros, así que el umbral por defecto de 20% de
-- tuplas muertas queda muy atrás.
alter table ads_campaign_daily set (autovacuum_vacuum_scale_factor = 0.02,
                                    autovacuum_analyze_scale_factor = 0.01);


-- El worker reescribe un día completo: lo que Amazon no mandó en el refresco deja
-- de existir para ese día. Espeja a replace_search_term_day.
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
        purchases_7d, sales_7d, purchases_14d, sales_14d, currency_code
    )
    select p_profile_id, p_day, row_data.campaign_id, row_data.impressions, row_data.clicks,
           row_data.cost, row_data.purchases_7d, row_data.sales_7d, row_data.purchases_14d,
           row_data.sales_14d, row_data.currency_code
      from jsonb_populate_recordset(null::ads_campaign_daily, p_rows) as row_data;

    get diagnostics inserted_count = row_count;
    return inserted_count;
end;
$$;


-- El universo manda: arranca en ads_campaign y las métricas entran por left join,
-- así una campaña sin actividad en el rango sigue apareciendo en ceros.
create or replace function campaigns_between(p_profile_id text, p_from date, p_to date)
returns table (
    campaign_id      text,
    name             text,
    state            text,
    targeting_type   text,
    start_date       date,
    budget_amount    numeric,
    budget_type      text,
    bidding_strategy text,
    portfolio_id     text,
    portfolio_name   text,
    impressions      bigint,
    clicks           bigint,
    cost             numeric,
    purchases_7d     bigint,
    sales_7d         numeric,
    purchases_14d    bigint,
    sales_14d        numeric,
    currency_code    text
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
               max(daily.currency_code)         as currency_code
          from ads_campaign_daily daily
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
           coalesce(totals.currency_code, '')        as currency_code
      from ads_campaign campaign
      left join totals on totals.campaign_id = campaign.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id
            and portfolio.portfolio_id = campaign.portfolio_id
     where campaign.profile_id = p_profile_id
     order by campaign.name;
$$;


-- Hasta acá toda fila de ads_report_requests era implícitamente un spSearchTerm.
-- La columna es aditiva y con default, así que las filas y el código existentes no
-- se enteran, y claim_report_requests reclama por status — no hace falta tocarla.
alter table ads_report_requests
    add column if not exists report_kind text not null default 'search_terms';


-- Igual que la versión de 4 argumentos, más los tipos de report a reclamar. Sin esto los
-- chunks de campañas compiten por el mismo cupo de in-flight que los de search terms y
-- demoran el sync nocturno de las cuentas pesadas.
--
-- La firma vieja queda viva a propósito: durante el deploy conviven la imagen anterior del
-- worker y esta base. Es seguro porque la imagen anterior no planifica campañas, así que su
-- claim sin filtro sólo encuentra pedidos de search terms. Deja de serlo si corren dos workers
-- a la vez con imágenes distintas: el viejo reclamaría chunks de campañas. Una migración
-- posterior puede borrarla cuando ya no la llame nadie.
create or replace function claim_report_requests(p_holder text, p_statuses text[], p_kinds text[],
                                                 p_limit int, p_lease_seconds int)
returns setof ads_report_requests
language sql
as $$
    update ads_report_requests request
       set lease_holder = p_holder,
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           updated_at = now()
      from (
          select id
            from ads_report_requests
           where status = any (p_statuses)
             and report_kind = any (p_kinds)
             and (lease_holder = '' or lease_expires_at is null or lease_expires_at < now())
             and (status <> 'requested' or next_poll_at is null or next_poll_at <= now())
           order by created_at, id
           limit greatest(p_limit, 0)
           for update skip locked
      ) due
     where request.id = due.id
    returning request.*;
$$;


-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla nueva, y
-- Postgres da EXECUTE a public sobre toda función nueva.
revoke all on ads_campaign, ads_campaign_daily from web_user;
revoke all on function replace_campaign_day(text, date, jsonb),
                       campaigns_between(text, date, date),
                       claim_report_requests(text, text[], text[], int, int)
  from public, web_user;

grant select on ads_campaign, ads_campaign_daily to web_user;
grant execute on function campaigns_between(text, date, date) to web_user;

grant select, insert, update on ads_campaign, ads_campaign_daily to integ_worker;
grant delete on ads_campaign, ads_campaign_daily to integ_worker;
grant execute on function replace_campaign_day(text, date, jsonb),
                          claim_report_requests(text, text[], text[], int, int)
  to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto, el primer insert del worker con report_kind
-- falla con PGRST204 hasta que alguien lo reinicie a mano.
notify pgrst, 'reload schema';

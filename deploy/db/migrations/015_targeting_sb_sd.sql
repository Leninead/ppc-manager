-- 015 — targeting de SP, SB y SD, y campañas de Sponsored Brands y Sponsored Display.
--
-- Aditiva: las tablas de campañas SP (013) y campaigns_between no cambian, así el análisis IA
-- y el MCP, que leen sólo SP, siguen igual. SB y SD tienen su propia foto y sus métricas, y los
-- targets de los tres productos van a ads_target / ads_target_daily con ad_product.
--
-- Igual que con las campañas, un report v3 sólo trae lo que tuvo actividad (medido en una
-- cuenta real: el spTargeting de un día trajo 3.620 de 35.076 targets habilitados). El universo
-- sale de las listas de entidades y las métricas entran por left join.
--
-- Las listas de SB, SD y targets se piden sólo con estados habilitado y pausado: lo archivado o
-- borrado no vuelve a aparecer. Cada lista se guarda con un único seen_at, así la lectura toma
-- sólo lo que estaba en la última lista y un target archivado no queda "habilitado" para siempre.

begin;

create table if not exists ads_sb_sd_campaign (
    profile_id         text not null collate "C",
    ad_product         text not null collate "C" check (ad_product in ('SB', 'SD')),
    campaign_id        text not null collate "C",
    name               text not null default '',
    state              text not null default '',
    budget_amount      numeric(14,4),
    budget_type        text not null default '',
    cost_type          text not null default '',
    portfolio_id       text not null default '',
    start_date         date,
    -- Sólo SB: los reports v3 de SB en preview no traen las campañas con false (verificado: 0 de 31).
    is_multi_ad_groups boolean,
    goal               text not null default '',
    tactic             text not null default '',
    -- SB: MANUAL o la estrategia de la puja automática. SD: la optimización de sus ad groups
    -- (clicks, conversions, reach), separadas por coma si difieren. La página la traduce.
    bid_strategy       text not null default '',
    seen_at            timestamptz not null default now(),
    primary key (profile_id, ad_product, campaign_id)
);


create table if not exists ads_sb_sd_campaign_daily (
    profile_id             text   not null collate "C",
    ad_product             text   not null collate "C" check (ad_product in ('SB', 'SD')),
    report_date            date   not null,
    campaign_id            text   not null collate "C",
    impressions            bigint not null default 0,
    clicks                 bigint not null default 0,
    cost                   numeric(14,4) not null default 0,
    -- 14 días, clicks o vistas: lo que Campaign Manager muestra como Purchases / Sales.
    purchases              bigint not null default 0,
    sales                  numeric(14,4) not null default 0,
    -- 14 días, sólo clicks: lo comparable con SP.
    purchases_clicks       bigint not null default 0,
    sales_clicks           numeric(14,4) not null default 0,
    new_to_brand_purchases bigint not null default 0,
    new_to_brand_sales     numeric(14,4) not null default 0,
    -- viewableImpressions en SB, impressionsViews en SD: el mismo concepto con dos nombres.
    viewable_impressions   bigint not null default 0,
    top_of_search_is       numeric(7,4),
    cost_type              text   not null default '',
    budget_amount          numeric(14,4),
    currency_code          text   not null default '',
    -- v3: los reportes de Reporting v3. v2: el reporte v2 de SB, el único que trae las campañas SB del
    -- formato anterior (isMultiAdGroupsEnabled = false). Cada fuente reescribe sólo sus filas del día.
    source                 text   not null default 'v3' check (source in ('v3', 'v2')),
    ingested_at            timestamptz not null default now(),
    -- La fecha antes del producto, como en ads_campaign_daily: las lecturas piden un rango de
    -- fechas de todos los productos juntos.
    primary key (profile_id, report_date, ad_product, campaign_id)
);
alter table ads_sb_sd_campaign_daily set (autovacuum_vacuum_scale_factor = 0.02,
                                          autovacuum_analyze_scale_factor = 0.01);


create table if not exists ads_target (
    profile_id  text not null collate "C",
    ad_product  text not null collate "C" check (ad_product in ('SP', 'SB', 'SD')),
    target_id   text not null collate "C",
    campaign_id text not null collate "C",
    ad_group_id text not null default '',
    -- keyword | product | auto | theme | audience
    target_kind text not null default '',
    target_text text not null default '',
    match_type  text not null default '',
    state       text not null default '',
    bid         numeric(14,4),
    seen_at     timestamptz not null default now(),
    primary key (profile_id, ad_product, target_id)
);
-- Sin este índice, graduation_targets_between recorre la lista entera del perfil por cada campaña
-- habilitada: medido en una cuenta real, 32 s contra 0,1 s.
create index if not exists ads_target_campaign_idx on ads_target (profile_id, ad_product, campaign_id);


create table if not exists ads_target_daily (
    profile_id       text   not null collate "C",
    ad_product       text   not null collate "C" check (ad_product in ('SP', 'SB', 'SD')),
    report_date      date   not null,
    target_id        text   not null collate "C",
    campaign_id      text   not null collate "C",
    ad_group_id      text   not null default '',
    target_kind      text   not null default '',
    target_text      text   not null default '',
    match_type       text   not null default '',
    impressions      bigint not null default 0,
    clicks           bigint not null default 0,
    cost             numeric(14,4) not null default 0,
    -- SP: atribución por clicks a 7 y 14 días.
    purchases_7d     bigint not null default 0,
    sales_7d         numeric(14,4) not null default 0,
    purchases_14d    bigint not null default 0,
    sales_14d        numeric(14,4) not null default 0,
    -- SB y SD: 14 días con clicks o vistas, y sólo clicks.
    purchases        bigint not null default 0,
    sales            numeric(14,4) not null default 0,
    purchases_clicks bigint not null default 0,
    sales_clicks     numeric(14,4) not null default 0,
    top_of_search_is numeric(7,4),
    currency_code    text   not null default '',
    ingested_at      timestamptz not null default now(),
    primary key (profile_id, report_date, ad_product, target_id)
);
alter table ads_target_daily set (autovacuum_vacuum_scale_factor = 0.02,
                                  autovacuum_analyze_scale_factor = 0.01);


-- Reescriben el día completo de un producto: lo que Amazon no mandó deja de existir para ese día.
-- Espejan a replace_campaign_day, con el producto como parte de la clave.
create or replace function replace_sb_sd_campaign_day(p_profile_id text, p_ad_product text, p_day date,
                                                      p_rows jsonb, p_source text default 'v3')
returns integer
language plpgsql
set statement_timeout = '120s'
as $$
declare
    inserted_count integer;
begin
    if p_ad_product not in ('SB', 'SD') then
        raise exception 'replace_sb_sd_campaign_day: unknown ad product %', p_ad_product;
    end if;
    if p_source not in ('v3', 'v2') or (p_source = 'v2' and p_ad_product <> 'SB') then
        raise exception 'replace_sb_sd_campaign_day: unknown source % for %', p_source, p_ad_product;
    end if;
    -- Un payload nulo o que no sea array caería en el delete y borraría el día.
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'replace_sb_sd_campaign_day: p_rows must be a json array';
    end if;

    if jsonb_array_length(p_rows) = 0 then
        if exists (select 1 from ads_sb_sd_campaign_daily
                    where profile_id = p_profile_id and ad_product = p_ad_product and report_date = p_day
                      and source = p_source) then
            return -1;
        end if;
        return 0;
    end if;

    delete from ads_sb_sd_campaign_daily
     where profile_id = p_profile_id and ad_product = p_ad_product and report_date = p_day and source = p_source;

    insert into ads_sb_sd_campaign_daily (
        profile_id, ad_product, report_date, campaign_id, impressions, clicks, cost, purchases, sales,
        purchases_clicks, sales_clicks, new_to_brand_purchases, new_to_brand_sales, viewable_impressions,
        top_of_search_is, cost_type, budget_amount, currency_code, source
    )
    select p_profile_id, p_ad_product, p_day, row_data.campaign_id,
           coalesce(row_data.impressions, 0), coalesce(row_data.clicks, 0), coalesce(row_data.cost, 0),
           coalesce(row_data.purchases, 0), coalesce(row_data.sales, 0),
           coalesce(row_data.purchases_clicks, 0), coalesce(row_data.sales_clicks, 0),
           coalesce(row_data.new_to_brand_purchases, 0), coalesce(row_data.new_to_brand_sales, 0),
           coalesce(row_data.viewable_impressions, 0), row_data.top_of_search_is,
           coalesce(row_data.cost_type, ''), row_data.budget_amount, coalesce(row_data.currency_code, ''), p_source
      from jsonb_populate_recordset(null::ads_sb_sd_campaign_daily, p_rows) as row_data
     -- El reporte v2 trae también las campañas que v3 ya cubre (medido: las 587 con las mismas cifras): de
     -- ese reporte entran sólo las del formato anterior, o el mismo gasto quedaría dos veces.
     where p_source = 'v3' or exists (
           select 1 from ads_sb_sd_campaign listed
            where listed.profile_id = p_profile_id and listed.ad_product = 'SB'
              and listed.campaign_id = row_data.campaign_id and listed.is_multi_ad_groups = false);

    get diagnostics inserted_count = row_count;
    return inserted_count;
end;
$$;


create or replace function replace_target_day(p_profile_id text, p_ad_product text, p_day date, p_rows jsonb)
returns integer
language plpgsql
set statement_timeout = '120s'
as $$
declare
    inserted_count integer;
begin
    if p_ad_product not in ('SP', 'SB', 'SD') then
        raise exception 'replace_target_day: unknown ad product %', p_ad_product;
    end if;
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'replace_target_day: p_rows must be a json array';
    end if;

    if jsonb_array_length(p_rows) = 0 then
        if exists (select 1 from ads_target_daily
                    where profile_id = p_profile_id and ad_product = p_ad_product and report_date = p_day) then
            return -1;
        end if;
        return 0;
    end if;

    delete from ads_target_daily
     where profile_id = p_profile_id and ad_product = p_ad_product and report_date = p_day;

    insert into ads_target_daily (
        profile_id, ad_product, report_date, target_id, campaign_id, ad_group_id, target_kind, target_text,
        match_type, impressions, clicks, cost, purchases_7d, sales_7d, purchases_14d, sales_14d, purchases,
        sales, purchases_clicks, sales_clicks, top_of_search_is, currency_code
    )
    select p_profile_id, p_ad_product, p_day, row_data.target_id, row_data.campaign_id,
           coalesce(row_data.ad_group_id, ''), coalesce(row_data.target_kind, ''),
           coalesce(row_data.target_text, ''), coalesce(row_data.match_type, ''),
           coalesce(row_data.impressions, 0), coalesce(row_data.clicks, 0), coalesce(row_data.cost, 0),
           coalesce(row_data.purchases_7d, 0), coalesce(row_data.sales_7d, 0),
           coalesce(row_data.purchases_14d, 0), coalesce(row_data.sales_14d, 0),
           coalesce(row_data.purchases, 0), coalesce(row_data.sales, 0),
           coalesce(row_data.purchases_clicks, 0), coalesce(row_data.sales_clicks, 0),
           row_data.top_of_search_is, coalesce(row_data.currency_code, '')
      from jsonb_populate_recordset(null::ads_target_daily, p_rows) as row_data;

    get diagnostics inserted_count = row_count;
    return inserted_count;
end;
$$;


-- Si ya cargó la historia del reporte v2 de SB: hasta entonces sus días están a medias, y las campañas del formato
-- anterior se leen sin métricas en vez de con una parte de ellas.
create or replace function sb_legacy_history_done(p_profile_id text)
returns boolean
language sql
stable
as $$
    select exists (
        select 1 from integration_sync_jobs job
         where job.integration_slug = 'amazon_ads' and job.external_account_id = p_profile_id
           and job.job_kind = 'sb_legacy_campaigns' and job.status = 'completed'
           and job.trigger in ('backfill', 'retry')
    );
$$;


-- Las campañas SB y SD de la última lista con sus métricas del rango sumadas. Como en
-- campaigns_between, el universo manda y una campaña sin actividad aparece en ceros.
-- metrics_known es falso para una SB del formato anterior mientras su historia v2 no terminó: sus ceros
-- no serían falta de actividad sino falta de datos, y no pueden leerse como una campaña que no entrega.
create or replace function product_campaigns_between(p_profile_id text, p_from date, p_to date)
returns table (
    ad_product           text,
    campaign_id          text,
    name                 text,
    state                text,
    start_date           date,
    budget_amount        numeric,
    budget_type          text,
    cost_type            text,
    portfolio_id         text,
    portfolio_name       text,
    is_multi_ad_groups   boolean,
    bid_strategy         text,
    metrics_known        boolean,
    impressions          bigint,
    clicks               bigint,
    cost                 numeric,
    purchases            bigint,
    sales                numeric,
    purchases_clicks     bigint,
    sales_clicks         numeric,
    viewable_impressions bigint,
    currency_code        text
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
               max(daily.currency_code)                as currency_code
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
           coalesce(totals.currency_code, '')               as currency_code
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


-- "Target Graduation": los targets habilitados, de campañas habilitadas, con sus impresiones del
-- rango; los candidatos son los que tienen 0. Vuelven todos, no sólo esos, para poder decir "N de M"
-- por producto, también cuando N es 0. Sólo cuenta los productos que ya tienen métricas de targeting
-- en el rango: sin ellas, todos sus targets parecerían sin impresiones. Tampoco las campañas SB
-- viejas: el reporte v2 que las trae es por campaña, y sus targets no tienen métricas.
create or replace function graduation_targets_between(p_profile_id text, p_from date, p_to date)
returns table (
    ad_product    text,
    target_id     text,
    campaign_id   text,
    campaign_name text,
    ad_group_id   text,
    target_kind   text,
    target_text   text,
    match_type    text,
    bid           numeric,
    impressions   bigint
)
language sql
stable
as $$
    with latest_targets as (
        select listed.ad_product, max(listed.seen_at) as seen_at
          from ads_target listed
         where listed.profile_id = p_profile_id
         group by listed.ad_product
    ),
    latest_campaigns as (
        select listed.ad_product, max(listed.seen_at) as seen_at
          from ads_sb_sd_campaign listed
         where listed.profile_id = p_profile_id
         group by listed.ad_product
    ),
    live_campaigns as (
        select 'SP'::text as ad_product, sp.campaign_id, sp.name
          from ads_campaign sp
         where sp.profile_id = p_profile_id and upper(sp.state) = 'ENABLED'
        union all
        select other.ad_product, other.campaign_id, other.name
          from ads_sb_sd_campaign other
          join latest_campaigns on latest_campaigns.ad_product = other.ad_product
                               and latest_campaigns.seen_at = other.seen_at
         where other.profile_id = p_profile_id and other.state = 'ENABLED'
           and (other.ad_product <> 'SB' or coalesce(other.is_multi_ad_groups, true))
    ),
    reported_products as (
        select distinct daily.ad_product
          from ads_target_daily daily
         where daily.profile_id = p_profile_id
           and daily.report_date between p_from and p_to
    ),
    activity as (
        select daily.ad_product, daily.target_id, sum(daily.impressions) as impressions
          from ads_target_daily daily
         where daily.profile_id = p_profile_id
           and daily.report_date between p_from and p_to
         group by daily.ad_product, daily.target_id
    )
    select target.ad_product, target.target_id, target.campaign_id, live.name as campaign_name,
           target.ad_group_id, target.target_kind, target.target_text, target.match_type, target.bid,
           coalesce(activity.impressions, 0)::bigint as impressions
      from ads_target target
      join latest_targets on latest_targets.ad_product = target.ad_product
                         and latest_targets.seen_at = target.seen_at
      join reported_products on reported_products.ad_product = target.ad_product
      join live_campaigns live on live.ad_product = target.ad_product and live.campaign_id = target.campaign_id
      left join activity on activity.ad_product = target.ad_product and activity.target_id = target.target_id
     where target.profile_id = p_profile_id and target.state = 'ENABLED'
     order by target.ad_product, live.name, target.target_text;
$$;


-- Los totales por día y por producto que suma el chat, de los reportes de campaña de SP, SB y SD. Salen de
-- las campañas y no de los search terms, que sólo traen términos con clicks (medido en una semana: 16.764
-- impresiones contra 135.934). Entran todas las campañas, también las archivadas: el gasto de un día es el
-- de ese día. SP trae sus dos atribuciones (7 y 14 días); SB y SD, la de Campaign Manager (clicks o vistas)
-- y la de sólo clicks. Con p_campaign, sólo las campañas cuyo nombre lo contiene.
create or replace function campaign_daily_totals(p_profile_id text, p_from date, p_to date,
                                                 p_campaign text default null)
returns table (
    report_date      date,
    ad_product       text,
    impressions      bigint,
    clicks           bigint,
    cost             numeric,
    purchases_7d     bigint,
    sales_7d         numeric,
    purchases_14d    bigint,
    sales_14d        numeric,
    purchases        bigint,
    sales            numeric,
    purchases_clicks bigint,
    sales_clicks     numeric,
    currency_code    text,
    campaign_names   text[]
)
language sql
stable
as $$
    -- Materializado: una sola consulta de la historia v2, no una por fila.
    with legacy as materialized (
        select sb_legacy_history_done(p_profile_id) as done
    ),
    activity as (
        select daily.report_date, 'SP'::text as ad_product, daily.impressions, daily.clicks, daily.cost,
               daily.purchases_7d, daily.sales_7d, daily.purchases_14d, daily.sales_14d,
               0::bigint as purchases, 0::numeric as sales, 0::bigint as purchases_clicks,
               0::numeric as sales_clicks, daily.currency_code, campaign.name
          from ads_campaign_daily daily
          left join ads_campaign campaign
                 on campaign.profile_id = daily.profile_id and campaign.campaign_id = daily.campaign_id
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
        union all
        select daily.report_date, daily.ad_product, daily.impressions, daily.clicks, daily.cost,
               0::bigint, 0::numeric, 0::bigint, 0::numeric,
               daily.purchases, daily.sales, daily.purchases_clicks, daily.sales_clicks, daily.currency_code,
               campaign.name
          from ads_sb_sd_campaign_daily daily
          cross join legacy
          left join ads_sb_sd_campaign campaign
                 on campaign.profile_id = daily.profile_id and campaign.ad_product = daily.ad_product
                and campaign.campaign_id = daily.campaign_id
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
           -- Las del formato anterior, sólo con su historia entera: como las muestra product_campaigns_between.
           and (daily.source = 'v3' or legacy.done)
    )
    select activity.report_date, activity.ad_product,
           sum(activity.impressions)::bigint, sum(activity.clicks)::bigint, sum(activity.cost),
           sum(activity.purchases_7d)::bigint, sum(activity.sales_7d),
           sum(activity.purchases_14d)::bigint, sum(activity.sales_14d),
           sum(activity.purchases)::bigint, sum(activity.sales),
           sum(activity.purchases_clicks)::bigint, sum(activity.sales_clicks),
           max(activity.currency_code),
           -- Sólo con filtro: quien llama tiene que decir qué campañas encontró el fragmento.
           case when p_campaign is null then null
                else array_agg(distinct activity.name order by activity.name)
                         filter (where activity.name is not null) end
      from activity
     -- strpos y no ilike: los nombres traen '_' y '%', que ilike leería como comodines.
     where p_campaign is null or strpos(lower(coalesce(activity.name, '')), lower(p_campaign)) > 0
     group by activity.report_date, activity.ad_product
     order by activity.report_date, activity.ad_product;
$$;


-- Lo mismo sumado por campaña en el rango, para repartir el total entre campañas, portfolios o productos.
-- Sólo las campañas con actividad: es un reparto del gasto, no la foto de campañas (campaigns_between).
create or replace function campaign_window_totals(p_profile_id text, p_from date, p_to date)
returns table (
    ad_product       text,
    campaign_id      text,
    campaign_name    text,
    portfolio_id     text,
    portfolio_name   text,
    impressions      bigint,
    clicks           bigint,
    cost             numeric,
    purchases_7d     bigint,
    sales_7d         numeric,
    purchases_14d    bigint,
    sales_14d        numeric,
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
               max(daily.currency_code) as currency_code
          from ads_sb_sd_campaign_daily daily
          cross join legacy
         where daily.profile_id = p_profile_id and daily.report_date between p_from and p_to
           and (daily.source = 'v3' or legacy.done)
         group by daily.ad_product, daily.campaign_id
    )
    select 'SP'::text, sp.campaign_id, coalesce(campaign.name, ''), coalesce(campaign.portfolio_id, ''),
           coalesce(portfolio.name, ''), sp.impressions, sp.clicks, sp.cost, sp.purchases_7d, sp.sales_7d,
           sp.purchases_14d, sp.sales_14d, 0::bigint, 0::numeric, 0::bigint, 0::numeric, sp.currency_code
      from sp
      left join ads_campaign campaign on campaign.profile_id = p_profile_id and campaign.campaign_id = sp.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id and portfolio.portfolio_id = campaign.portfolio_id
    union all
    select others.ad_product, others.campaign_id, coalesce(campaign.name, ''), coalesce(campaign.portfolio_id, ''),
           coalesce(portfolio.name, ''), others.impressions, others.clicks, others.cost, 0::bigint, 0::numeric,
           0::bigint, 0::numeric, others.purchases, others.sales, others.purchases_clicks, others.sales_clicks,
           others.currency_code
      from others
      left join ads_sb_sd_campaign campaign
             on campaign.profile_id = p_profile_id and campaign.ad_product = others.ad_product
            and campaign.campaign_id = others.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id and portfolio.portfolio_id = campaign.portfolio_id;
$$;


-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla nueva, y
-- Postgres da EXECUTE a public sobre toda función nueva.
revoke all on ads_sb_sd_campaign, ads_sb_sd_campaign_daily, ads_target, ads_target_daily from web_user;
revoke all on function replace_sb_sd_campaign_day(text, text, date, jsonb, text),
                       replace_target_day(text, text, date, jsonb),
                       sb_legacy_history_done(text),
                       product_campaigns_between(text, date, date),
                       graduation_targets_between(text, date, date),
                       campaign_daily_totals(text, date, date, text),
                       campaign_window_totals(text, date, date)
  from public, web_user;

grant select on ads_sb_sd_campaign, ads_sb_sd_campaign_daily, ads_target, ads_target_daily to web_user;
grant execute on function sb_legacy_history_done(text),
                          product_campaigns_between(text, date, date),
                          graduation_targets_between(text, date, date),
                          campaign_daily_totals(text, date, date, text),
                          campaign_window_totals(text, date, date)
  to web_user;

-- El análisis IA de Bulk Campañas lee también SB y SD: el worker de análisis (ai_worker) necesita la función
-- y sus tablas. ads_portfolios e integration_sync_jobs ya los lee desde la 010.
grant select on ads_sb_sd_campaign, ads_sb_sd_campaign_daily to ai_worker;
grant execute on function sb_legacy_history_done(text), product_campaigns_between(text, date, date) to ai_worker;

grant select, insert, update, delete on ads_sb_sd_campaign, ads_sb_sd_campaign_daily, ads_target,
                                        ads_target_daily
  to integ_worker;
grant execute on function replace_sb_sd_campaign_day(text, text, date, jsonb, text),
                          replace_target_day(text, text, date, jsonb)
  to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto, las tablas y funciones nuevas dan 404 hasta reiniciarlo.
notify pgrst, 'reload schema';

-- 018 — estructura de Sponsored Products desde los listados de Amazon Ads: ad groups, ajustes por
-- placement y negativos.
--
-- Aditiva. La estructura SP sale de los listados síncronos v3 y no de los reportes, porque un reporte sólo
-- trae lo que tuvo actividad. Medido en producción el 22/09: el 85,2% de los keywords y targets SP
-- habilitados de la lista no tiene ninguna fila de spTargeting en 60 días (el 98,9% de los pausados), y de
-- las campañas SP no aparecen en spCampaigns el 0,4% de las habilitadas y el 93,5% de las pausadas. Las
-- métricas diarias siguen saliendo de Reporting v3.
--
-- Cada listado es una foto diaria que se guarda sólo con upserts y un único seen_at, como las listas de la
-- 015 y la 017: la lectura toma la última lista, así lo que dejó de listarse no queda vivo para siempre.
-- ads_ad_group guarda los ad groups con su bid por defecto; ads_negative, los negativos de keyword y de
-- producto a nivel campaña y a nivel ad group; los ajustes por placement van en ads_campaign, porque salen
-- de la misma respuesta que ya se baja para las campañas.
--
-- Los negativos son la excepción: los de una cuenta grande no entran en un tick del worker (Shapermint US,
-- medido el 22/09: 371.407 negativos en 374 páginas de 1.000, unos 6 minutos a 0,95 s por página, y el
-- aviso de worker callado salta a los 5). El worker los lista por partes, con un tope de páginas por tick,
-- guarda en el job dónde quedó (integration_sync_jobs.progress) y, cuando termina la corrida, la anota en
-- ads_listing_snapshot. La lectura toma los negativos vistos desde el seen_at de la última corrida
-- completa: mientras otra corre se sigue viendo la anterior, y antes de la primera no hay negativos.
--
-- El bid efectivo vive en un solo lugar, la vista ads_target_bid: un keyword o target sin bid propio usa el
-- bid por defecto de su ad group. De ahí leen graduation_targets_between, que además deja afuera los
-- targets de ad groups pausados, y sp_structure_between, la estructura entera para los módulos y el chat.
-- sp_structure_counts cuenta sus filas por familia sin traerlas.

begin;

-- Hoy sólo se escribe SP; el producto va en la clave como en ads_target.
create table if not exists ads_ad_group (
    profile_id  text not null collate "C",
    ad_product  text not null collate "C" check (ad_product in ('SP', 'SB', 'SD')),
    ad_group_id text not null collate "C",
    campaign_id text not null collate "C",
    name        text not null default '',
    state       text not null default '',
    default_bid numeric(14,4),
    seen_at     timestamptz not null default now(),
    primary key (profile_id, ad_product, ad_group_id)
);


alter table ads_campaign
    add column if not exists placement_top_pct            integer,
    add column if not exists placement_product_page_pct   integer,
    add column if not exists placement_rest_of_search_pct integer,
    add column if not exists amazon_business_pct          integer;

comment on column ads_campaign.placement_top_pct is
    'Ajuste de puja en top of search (PLACEMENT_TOP), de 0 a 900 %. 0: sin ajuste. '
    'NULL: desconocido (sin listar desde la 018, Amazon no mandó dynamicBidding, o el porcentaje no era entero).';
comment on column ads_campaign.placement_product_page_pct is
    'Ajuste de puja en páginas de producto (PLACEMENT_PRODUCT_PAGE), de 0 a 900 %. 0: sin ajuste. '
    'NULL: desconocido (sin listar desde la 018, Amazon no mandó dynamicBidding, o el porcentaje no era entero).';
comment on column ads_campaign.placement_rest_of_search_pct is
    'Ajuste de puja en el resto de la búsqueda (PLACEMENT_REST_OF_SEARCH), de 0 a 900 %. 0: sin ajuste. '
    'NULL: desconocido (sin listar desde la 018, Amazon no mandó dynamicBidding, o el porcentaje no era entero).';
comment on column ads_campaign.amazon_business_pct is
    'Ajuste de puja en Amazon Business (SITE_AMAZON_BUSINESS), de 0 a 900 %. 0: sin ajuste. '
    'NULL: desconocido (sin listar desde la 018, Amazon no mandó dynamicBidding, o el porcentaje no era entero).';


-- Los cuatro listados de negativos: de keyword y de producto, a nivel campaña y a nivel ad group. El nivel
-- y el tipo van en la clave porque cada listado tiene sus propios ids (que no choquen no está verificado).
create table if not exists ads_negative (
    profile_id    text not null collate "C",
    ad_product    text not null collate "C" check (ad_product in ('SP', 'SB', 'SD')),
    negative_id   text not null collate "C",
    level         text not null check (level in ('campaign', 'ad_group')),
    negative_kind text not null check (negative_kind in ('keyword', 'product')),
    campaign_id   text not null collate "C",
    -- '' en los negativos de campaña.
    ad_group_id   text not null default '',
    -- El keyword, o la expresión del producto: asin="..." o brand="...".
    negative_text text not null default '',
    -- NEGATIVE_EXACT | NEGATIVE_PHRASE | NEGATIVE_BROAD | OTHER; '' en los de producto.
    match_type    text not null default '',
    state         text not null default '',
    seen_at       timestamptz not null default now(),
    primary key (profile_id, ad_product, level, negative_kind, negative_id)
);
-- Para leer los negativos de una campaña sin recorrer los de todo el perfil.
create index if not exists ads_negative_campaign_idx on ads_negative (profile_id, ad_product, campaign_id);


alter table integration_sync_jobs add column if not exists progress jsonb;

comment on column integration_sync_jobs.progress is
    'Dónde quedó un listado que se hace por partes, entre un tick del worker y el siguiente: '
    '{"listing": 0..3, "next_token": "<token, o vacío>", "seen_at": "<ISO UTC de la corrida>", '
    '"rows": <filas guardadas hasta ahí>, "pages": <páginas leídas del listado en curso>}. NULL: el job no '
    'está a mitad de un listado. Un 429 lo deja '
    'donde estaba; cualquier otro fallo lo vuelve a NULL y la corrida empieza de nuevo, porque un token de '
    'página puede no durar minutos.';


-- La última corrida COMPLETA de un listado que se hace por partes. Lo que guarda una corrida sólo vale
-- cuando termina, así que la lectura toma lo visto desde el seen_at de la última completa.
create table if not exists ads_listing_snapshot (
    profile_id   text not null collate "C",
    -- 'sp_negatives' hoy.
    listing      text not null collate "C",
    -- El seen_at que llevan todas las filas de esa corrida.
    seen_at      timestamptz not null,
    rows         integer not null,
    completed_at timestamptz not null default now(),
    primary key (profile_id, listing)
);


-- Cada target con su bid efectivo y el último estado, nombre y bid por defecto conocidos de su ad group. Los
-- ad groups no se filtran por su última lista: las dos listas pueden correr con horas de diferencia, y un ad
-- group que no se listó todavía vuelve con nombre y estado vacíos. Quien lee elige la última lista de targets.
-- Es una vista y no una función que devuelve text: esa función pierde el collate "C" de las columnas, el cruce
-- con las campañas deja de usar ads_target_campaign_idx y graduation pasa de 0,05 s a 16 s (medido el 22/09
-- con Shapermint US, 44.526 targets).
create or replace view ads_target_bid with (security_invoker = true) as
select target.profile_id, target.ad_product, target.target_id, target.campaign_id, target.ad_group_id,
       target.target_kind, target.target_text, target.match_type, target.state, target.seen_at,
       target.bid as own_bid,
       coalesce(ad_group.name, '')  as ad_group_name,
       coalesce(ad_group.state, '') as ad_group_state,
       ad_group.default_bid,
       -- Spec de SP v3: un keyword o target que se lista sin bid usa el defaultBid de su ad group.
       coalesce(target.bid, ad_group.default_bid) as bid
  from ads_target target
  left join ads_ad_group ad_group
         on ad_group.profile_id = target.profile_id
        and ad_group.ad_product = target.ad_product
        and ad_group.ad_group_id = target.ad_group_id;


-- "Target Graduation": los targets habilitados, de campañas habilitadas, con sus impresiones del
-- rango; los candidatos son los que tienen 0. Vuelven todos, no sólo esos, para poder decir "N de M"
-- por producto, también cuando N es 0. Los de ad groups pausados quedan afuera; un ad group que nunca se
-- listó cuenta como habilitado, así nada cambia antes de su primera lista y SB y SD siguen igual. El bid es
-- el efectivo: el propio o, si no tiene, el bid por defecto de su ad group. Sólo cuenta los productos que
-- ya tienen métricas de targeting en el rango: sin ellas, todos sus targets parecerían sin impresiones.
-- Tampoco las campañas SB viejas: el reporte v2 que las trae es por campaña, y sus targets no tienen
-- métricas.
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
      from ads_target_bid target
      join latest_targets on latest_targets.ad_product = target.ad_product
                         and latest_targets.seen_at = target.seen_at
      join reported_products on reported_products.ad_product = target.ad_product
      join live_campaigns live on live.ad_product = target.ad_product and live.campaign_id = target.campaign_id
      left join activity on activity.ad_product = target.ad_product and activity.target_id = target.target_id
     where target.profile_id = p_profile_id and target.state = 'ENABLED'
       and target.ad_group_state in ('', 'ENABLED')
     order by target.ad_product, live.name, target.target_text;
$$;


-- La estructura SP de la cuenta en una sola tabla, una fila por entidad y entity diciendo cuál: campaign,
-- bidding_adjustment (un ajuste por placement), ad_group, keyword, product_targeting, product_ad y los
-- negativos (negative_keyword, campaign_negative_keyword, negative_product_targeting,
-- campaign_negative_product_targeting). Cada familia sale de su última lista (los negativos, de lo visto
-- desde su última corrida completa) y trae su estado sin filtrar (las campañas, también las archivadas):
-- quien lee decide. Las métricas del rango van sólo en campañas, keywords y product targets, y
-- metrics_known dice si hay reportes del rango: sin ellos, los ceros no son falta de actividad sino falta de
-- datos. p_entities elige las familias y p_campaign_ids, las campañas. Vuelve sin orden: el lector de la app
-- ordena, y un orden acá obligaría a sp_structure_counts a ordenar lo que sólo cuenta.
create or replace function sp_structure_between(p_profile_id text, p_from date, p_to date,
                                                p_entities text[] default null,
                                                p_campaign_ids text[] default null)
returns table (
    entity           text,
    campaign_id      text,
    ad_group_id      text,
    entity_id        text,
    campaign_name    text,
    ad_group_name    text,
    portfolio_id     text,
    portfolio_name   text,
    state            text,
    targeting_type   text,
    budget_amount    numeric,
    budget_type      text,
    bidding_strategy text,
    placement        text,
    percentage       integer,
    asin             text,
    sku              text,
    target_kind      text,
    target_text      text,
    match_type       text,
    default_bid      numeric,
    own_bid          numeric,
    bid              numeric,
    impressions      bigint,
    clicks           bigint,
    cost             numeric,
    purchases_7d     bigint,
    sales_7d         numeric,
    purchases_14d    bigint,
    sales_14d        numeric,
    metrics_known    boolean,
    currency_code    text,
    listed_at        timestamptz
)
language sql
stable
as $$
    with window_coverage as (
        select exists (select 1 from ads_campaign_daily daily
                        where daily.profile_id = p_profile_id
                          and daily.report_date between p_from and p_to) as campaign_metrics_known,
               exists (select 1 from ads_target_daily daily
                        where daily.profile_id = p_profile_id and daily.ad_product = 'SP'
                          and daily.report_date between p_from and p_to) as target_metrics_known,
               coalesce((select max(daily.currency_code) from ads_campaign_daily daily
                          where daily.profile_id = p_profile_id
                            and daily.report_date between p_from and p_to), '') as currency_code
    ),
    campaign_totals as (
        select daily.campaign_id,
               sum(daily.impressions)::bigint   as impressions,
               sum(daily.clicks)::bigint        as clicks,
               sum(daily.cost)                  as cost,
               sum(daily.purchases_7d)::bigint  as purchases_7d,
               sum(daily.sales_7d)              as sales_7d,
               sum(daily.purchases_14d)::bigint as purchases_14d,
               sum(daily.sales_14d)             as sales_14d
          from ads_campaign_daily daily
         where daily.profile_id = p_profile_id
           and daily.report_date between p_from and p_to
         group by daily.campaign_id
    ),
    target_totals as (
        select daily.target_id,
               sum(daily.impressions)::bigint   as impressions,
               sum(daily.clicks)::bigint        as clicks,
               sum(daily.cost)                  as cost,
               sum(daily.purchases_7d)::bigint  as purchases_7d,
               sum(daily.sales_7d)              as sales_7d,
               sum(daily.purchases_14d)::bigint as purchases_14d,
               sum(daily.sales_14d)             as sales_14d
          from ads_target_daily daily
         where daily.profile_id = p_profile_id and daily.ad_product = 'SP'
           and daily.report_date between p_from and p_to
         group by daily.target_id
    ),
    listed_campaigns as (
        select campaign.*
          from ads_campaign campaign
         where campaign.profile_id = p_profile_id
           and campaign.seen_at = (select max(listed.seen_at) from ads_campaign listed
                                    where listed.profile_id = p_profile_id)
           and (p_campaign_ids is null or campaign.campaign_id = any (p_campaign_ids))
    ),
    listed_ad_groups as (
        select ad_group.*
          from ads_ad_group ad_group
         where ad_group.profile_id = p_profile_id and ad_group.ad_product = 'SP'
           and ad_group.seen_at = (select max(listed.seen_at) from ads_ad_group listed
                                    where listed.profile_id = p_profile_id and listed.ad_product = 'SP')
           and (p_campaign_ids is null or ad_group.campaign_id = any (p_campaign_ids))
    ),
    listed_targets as (
        select target.*,
               case when target.target_kind = 'keyword' then 'keyword' else 'product_targeting' end as entity
          from ads_target_bid target
         where target.profile_id = p_profile_id and target.ad_product = 'SP'
           and target.seen_at = (select max(listed.seen_at) from ads_target listed
                                  where listed.profile_id = p_profile_id and listed.ad_product = 'SP')
           and (p_campaign_ids is null or target.campaign_id = any (p_campaign_ids))
    ),
    listed_product_ads as (
        select product_ad.*
          from ads_product_ad product_ad
         where product_ad.profile_id = p_profile_id
           and product_ad.seen_at = (select max(listed.seen_at) from ads_product_ad listed
                                      where listed.profile_id = p_profile_id)
           and (p_campaign_ids is null or product_ad.campaign_id = any (p_campaign_ids))
    ),
    listed_negatives as (
        select negative.*, snapshot.seen_at as listed_at,
               case when negative.level = 'ad_group' and negative.negative_kind = 'keyword'
                        then 'negative_keyword'
                    when negative.level = 'campaign' and negative.negative_kind = 'keyword'
                        then 'campaign_negative_keyword'
                    when negative.level = 'ad_group' then 'negative_product_targeting'
                    else 'campaign_negative_product_targeting' end as entity
          from ads_negative negative
          -- Lo visto desde la última corrida completa, con la hora en que empezó: una a medias ya re-estampó parte
          -- de las filas, y sin ninguna completa no vuelve nada.
          join ads_listing_snapshot snapshot
            on snapshot.profile_id = p_profile_id and snapshot.listing = 'sp_negatives'
           and negative.seen_at >= snapshot.seen_at
         where negative.profile_id = p_profile_id and negative.ad_product = 'SP'
           and (p_campaign_ids is null or negative.campaign_id = any (p_campaign_ids))
    ),
    campaign_rows as (
        select 'campaign' as entity, campaign.campaign_id, '' as ad_group_id, campaign.campaign_id as entity_id,
               campaign.name as campaign_name, '' as ad_group_name, campaign.portfolio_id,
               coalesce(portfolio.name, '') as portfolio_name,
               campaign.state, campaign.targeting_type, campaign.budget_amount, campaign.budget_type,
               campaign.bidding_strategy,
               '' as placement, null::integer as percentage, '' as asin, '' as sku,
               '' as target_kind, '' as target_text, '' as match_type,
               null::numeric as default_bid, null::numeric as own_bid, null::numeric as bid,
               coalesce(totals.impressions, 0)::bigint as impressions, coalesce(totals.clicks, 0)::bigint as clicks,
               coalesce(totals.cost, 0) as cost,
               coalesce(totals.purchases_7d, 0)::bigint as purchases_7d, coalesce(totals.sales_7d, 0) as sales_7d,
               coalesce(totals.purchases_14d, 0)::bigint as purchases_14d, coalesce(totals.sales_14d, 0) as sales_14d,
               coverage.campaign_metrics_known as metrics_known, coverage.currency_code,
               campaign.seen_at as listed_at
          from listed_campaigns campaign
          cross join window_coverage coverage
          left join campaign_totals totals on totals.campaign_id = campaign.campaign_id
          left join ads_portfolios portfolio
                 on portfolio.profile_id = p_profile_id
                and portfolio.portfolio_id = campaign.portfolio_id
         where p_entities is null or 'campaign' = any (p_entities)
    ),
    bidding_adjustment_rows as (
        select 'bidding_adjustment' as entity, campaign.campaign_id, '' as ad_group_id, '' as entity_id,
               campaign.name as campaign_name, '' as ad_group_name, '' as portfolio_id, '' as portfolio_name,
               campaign.state, '' as targeting_type, null::numeric as budget_amount, '' as budget_type,
               campaign.bidding_strategy,
               adjustment.placement, adjustment.percentage, '' as asin, '' as sku,
               '' as target_kind, '' as target_text, '' as match_type,
               null::numeric as default_bid, null::numeric as own_bid, null::numeric as bid,
               null::bigint as impressions, null::bigint as clicks, null::numeric as cost,
               null::bigint as purchases_7d, null::numeric as sales_7d,
               null::bigint as purchases_14d, null::numeric as sales_14d,
               false as metrics_known, coverage.currency_code, campaign.seen_at as listed_at
          from listed_campaigns campaign
          cross join lateral (values ('PLACEMENT_TOP', campaign.placement_top_pct),
                                     ('PLACEMENT_PRODUCT_PAGE', campaign.placement_product_page_pct),
                                     ('PLACEMENT_REST_OF_SEARCH', campaign.placement_rest_of_search_pct),
                                     ('SITE_AMAZON_BUSINESS', campaign.amazon_business_pct))
                        as adjustment (placement, percentage)
          cross join window_coverage coverage
         where adjustment.percentage is not null
           and (p_entities is null or 'bidding_adjustment' = any (p_entities))
    ),
    ad_group_rows as (
        select 'ad_group' as entity, ad_group.campaign_id, ad_group.ad_group_id, ad_group.ad_group_id as entity_id,
               coalesce(campaign.name, '') as campaign_name, ad_group.name as ad_group_name,
               '' as portfolio_id, '' as portfolio_name,
               ad_group.state, '' as targeting_type, null::numeric as budget_amount, '' as budget_type,
               '' as bidding_strategy,
               '' as placement, null::integer as percentage, '' as asin, '' as sku,
               '' as target_kind, '' as target_text, '' as match_type,
               ad_group.default_bid, null::numeric as own_bid, null::numeric as bid,
               null::bigint as impressions, null::bigint as clicks, null::numeric as cost,
               null::bigint as purchases_7d, null::numeric as sales_7d,
               null::bigint as purchases_14d, null::numeric as sales_14d,
               false as metrics_known, coverage.currency_code, ad_group.seen_at as listed_at
          from listed_ad_groups ad_group
          cross join window_coverage coverage
          left join ads_campaign campaign
                 on campaign.profile_id = p_profile_id and campaign.campaign_id = ad_group.campaign_id
         where p_entities is null or 'ad_group' = any (p_entities)
    ),
    target_rows as (
        select target.entity, target.campaign_id, target.ad_group_id, target.target_id as entity_id,
               coalesce(campaign.name, '') as campaign_name, target.ad_group_name,
               '' as portfolio_id, '' as portfolio_name,
               target.state, '' as targeting_type, null::numeric as budget_amount, '' as budget_type,
               '' as bidding_strategy,
               '' as placement, null::integer as percentage, '' as asin, '' as sku,
               target.target_kind, target.target_text, target.match_type,
               target.default_bid, target.own_bid, target.bid,
               coalesce(totals.impressions, 0)::bigint as impressions, coalesce(totals.clicks, 0)::bigint as clicks,
               coalesce(totals.cost, 0) as cost,
               coalesce(totals.purchases_7d, 0)::bigint as purchases_7d, coalesce(totals.sales_7d, 0) as sales_7d,
               coalesce(totals.purchases_14d, 0)::bigint as purchases_14d, coalesce(totals.sales_14d, 0) as sales_14d,
               coverage.target_metrics_known as metrics_known, coverage.currency_code,
               target.seen_at as listed_at
          from listed_targets target
          cross join window_coverage coverage
          left join target_totals totals on totals.target_id = target.target_id
          left join ads_campaign campaign
                 on campaign.profile_id = p_profile_id and campaign.campaign_id = target.campaign_id
         where p_entities is null or target.entity = any (p_entities)
    ),
    product_ad_rows as (
        select 'product_ad' as entity, product_ad.campaign_id, product_ad.ad_group_id,
               product_ad.ad_id as entity_id,
               coalesce(campaign.name, '') as campaign_name, coalesce(ad_group.name, '') as ad_group_name,
               '' as portfolio_id, '' as portfolio_name,
               product_ad.state, '' as targeting_type, null::numeric as budget_amount, '' as budget_type,
               '' as bidding_strategy,
               '' as placement, null::integer as percentage, product_ad.asin, product_ad.sku,
               '' as target_kind, '' as target_text, '' as match_type,
               null::numeric as default_bid, null::numeric as own_bid, null::numeric as bid,
               null::bigint as impressions, null::bigint as clicks, null::numeric as cost,
               null::bigint as purchases_7d, null::numeric as sales_7d,
               null::bigint as purchases_14d, null::numeric as sales_14d,
               false as metrics_known, coverage.currency_code, product_ad.seen_at as listed_at
          from listed_product_ads product_ad
          cross join window_coverage coverage
          left join ads_campaign campaign
                 on campaign.profile_id = p_profile_id and campaign.campaign_id = product_ad.campaign_id
          left join ads_ad_group ad_group
                 on ad_group.profile_id = p_profile_id and ad_group.ad_product = 'SP'
                and ad_group.ad_group_id = product_ad.ad_group_id
         where p_entities is null or 'product_ad' = any (p_entities)
    ),
    negative_rows as (
        select negative.entity, negative.campaign_id, negative.ad_group_id, negative.negative_id as entity_id,
               coalesce(campaign.name, '') as campaign_name, coalesce(ad_group.name, '') as ad_group_name,
               '' as portfolio_id, '' as portfolio_name,
               negative.state, '' as targeting_type, null::numeric as budget_amount, '' as budget_type,
               '' as bidding_strategy,
               '' as placement, null::integer as percentage, '' as asin, '' as sku,
               negative.negative_kind as target_kind, negative.negative_text as target_text, negative.match_type,
               null::numeric as default_bid, null::numeric as own_bid, null::numeric as bid,
               null::bigint as impressions, null::bigint as clicks, null::numeric as cost,
               null::bigint as purchases_7d, null::numeric as sales_7d,
               null::bigint as purchases_14d, null::numeric as sales_14d,
               false as metrics_known, coverage.currency_code, negative.listed_at
          from listed_negatives negative
          cross join window_coverage coverage
          left join ads_campaign campaign
                 on campaign.profile_id = p_profile_id and campaign.campaign_id = negative.campaign_id
          left join ads_ad_group ad_group
                 on ad_group.profile_id = p_profile_id and ad_group.ad_product = 'SP'
                and ad_group.ad_group_id = negative.ad_group_id
         where p_entities is null or negative.entity = any (p_entities)
    ),
    structure_rows as (
        select * from campaign_rows
        union all select * from bidding_adjustment_rows
        union all select * from ad_group_rows
        union all select * from target_rows
        union all select * from product_ad_rows
        union all select * from negative_rows
    )
    select structure_rows.*
      from structure_rows;
$$;


-- Cuántas filas tiene cada familia de la estructura SP y cuándo se listó, de la cuenta o de sus campañas:
-- lo que el chat mira antes de leer filas, porque los negativos de una cuenta grande no se leen enteros.
-- Cuenta sobre sp_structure_between, así las reglas de qué lista vale viven en un solo lugar. Una familia
-- sin filas no vuelve, salvo los negativos: la última corrida completa dice que se listaron, así que con ella
-- vuelven las cuatro familias, en 0 las que no tienen ninguno en el alcance. Antes de la primera, no vuelven.
create or replace function sp_structure_counts(p_profile_id text, p_from date, p_to date,
                                               p_campaign_ids text[] default null)
returns table (
    entity      text,
    entity_rows bigint,
    listed_at   timestamptz
)
language sql
stable
as $$
    with counted as (
        select structure.entity, count(*) as entity_rows, max(structure.listed_at) as listed_at
          from sp_structure_between(p_profile_id, p_from, p_to, null, p_campaign_ids) structure
         group by structure.entity
    )
    select counted.entity, counted.entity_rows, counted.listed_at
      from counted
    union all
    select family.entity, 0::bigint, snapshot.seen_at
      from ads_listing_snapshot snapshot
     cross join unnest(array['negative_keyword', 'campaign_negative_keyword', 'negative_product_targeting',
                             'campaign_negative_product_targeting']) as family (entity)
     where snapshot.profile_id = p_profile_id and snapshot.listing = 'sp_negatives'
       and not exists (select 1 from counted where counted.entity = family.entity);
$$;


-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla nueva, y
-- Postgres da EXECUTE a public sobre toda función nueva.
revoke all on ads_ad_group, ads_negative, ads_listing_snapshot, ads_target_bid from web_user;
revoke all on function sp_structure_between(text, date, date, text[], text[]),
                       sp_structure_counts(text, date, date, text[])
  from public, web_user;

-- graduation_targets_between, las dos funciones de la estructura y la vista corren con los permisos de quien
-- las llama, y el MCP lee como web_user.
grant select on ads_ad_group, ads_negative, ads_listing_snapshot, ads_target_bid to web_user;
grant execute on function sp_structure_between(text, date, date, text[], text[]),
                          sp_structure_counts(text, date, date, text[])
  to web_user;

-- integration_sync_jobs.progress no necesita grant: la 009 le da al worker select, insert y update sobre la
-- tabla entera.
grant select, insert, update, delete on ads_ad_group, ads_negative to integ_worker;
grant select, insert, update on ads_listing_snapshot to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto, las tablas, las columnas y las funciones nuevas dan 404 hasta
-- reiniciarlo.
notify pgrst, 'reload schema';

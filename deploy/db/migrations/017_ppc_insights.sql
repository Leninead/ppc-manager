-- 017 — productos anunciados de Sponsored Products y el análisis IA de PPC Insights.
--
-- Aditiva. El reporte de search terms no trae el ASIN anunciado; lo trae el listado de productos
-- anunciados (/sp/productAds/list): cada anuncio dice su ad group, su ASIN y su SKU, también en cuentas
-- seller (medido el 21/09 contra la API real). Con eso cada search term se atribuye al ASIN de su ad group.
-- Como las otras listas, se guarda sólo con upserts: un anuncio archivado deja de listarse, y los search
-- terms viejos de su ad group siguen necesitando su ASIN.
--
-- El análisis de PPC Insights no se genera solo: lo pide el AM y lo corre el worker. request_ai_analysis
-- suma p_agent_version: con ella, datos ya analizados por una versión anterior del agente se pueden
-- volver a pedir. La huella sigue siendo una por datos y versión (ai_analyses_once), como en todos los
-- módulos; sin p_agent_version la función se comporta igual que en la 014.

begin;

create table if not exists ads_product_ad (
    profile_id  text not null collate "C",
    ad_id       text not null collate "C",
    campaign_id text not null collate "C",
    ad_group_id text not null collate "C",
    asin        text not null default '',
    sku         text not null default '',
    state       text not null default '',
    seen_at     timestamptz not null default now(),
    primary key (profile_id, ad_id)
);
create index if not exists ads_product_ad_ad_group_idx on ads_product_ad (profile_id, ad_group_id);


create or replace function ai_analysis_module_allowed(p_module text)
returns boolean
language sql
immutable
as $$
    select p_module in ('str', 'bid_optimizer', 'bulk_campaigns', 'ppc_insights');
$$;


-- Otra firma: se borra la de la 014 para que PostgREST no tenga dos candidatas con los mismos argumentos.
drop function if exists request_ai_analysis(text, text, date, date, text, jsonb, text, text);

create function request_ai_analysis(p_module text, p_subject_id text, p_window_start date,
                                    p_window_end date, p_lang text, p_params jsonb,
                                    p_input_digest text, p_requested_by text,
                                    p_agent_version text default '')
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
    wanted_version text := coalesce(p_agent_version, '');
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
       and (wanted_version = '' or analysis.agent_version = wanted_version)
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
        || case when wanted_version <> '' then jsonb_build_object('agent_version', wanted_version)
                else '{}'::jsonb end
    )
    returning id into new_job_id;

    return query select new_job_id, true, 'created'::text;
end;
$$;


-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla nueva, y
-- Postgres da EXECUTE a public sobre toda función nueva.
revoke all on ads_product_ad from web_user;
revoke all on function request_ai_analysis(text, text, date, date, text, jsonb, text, text, text)
  from public, web_user;

grant select on ads_product_ad to web_user;
grant execute on function request_ai_analysis(text, text, date, date, text, jsonb, text, text, text) to web_user;
-- El worker de análisis arma el payload de PPC Insights con el ASIN de cada ad group.
grant select on ads_product_ad to ai_worker;
grant select, insert, update, delete on ads_product_ad to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto, la tabla y la función nuevas dan 404 hasta reiniciarlo.
notify pgrst, 'reload schema';

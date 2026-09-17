-- Bid Optimizer analyses reuse ai_analyses (migration 010): its module column already separates
-- them from the Search Term Report's, and claim_ai_jobs claims any 'ai\_%' job kind.
--
-- What they do not have is somewhere to keep the rows the analysis was built from. M2 stores its
-- two lists in negative_records / harvest_records; naming a module's rows after M2's candidates
-- would only work for M2, so the generic column holds them for every module that comes after.

alter table ai_analyses
    add column if not exists records jsonb not null default '[]'::jsonb;

comment on column ai_analyses.records is
    'Rows the analysis was built from, in the order their row_ids were given. Modules other than str.';


-- Los dos RPCs que la app llama traían 'str' escrito a mano, así que un módulo nuevo recibía
-- 'invalid_request' y el AM leía "no se pudo pedir el análisis" sin ninguna causa. La lista de
-- módulos con análisis guardado vive ahora en un solo lugar: sumar el próximo es una línea.

create or replace function ai_analysis_module_allowed(p_module text)
returns boolean
language sql
immutable
as $$
    select p_module in ('str', 'bid_optimizer');
$$;


create or replace function save_ai_analysis_settings(p_module text, p_subject_id text, p_params jsonb,
                                                     p_updated_by text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
    if not ai_analysis_module_allowed(p_module) or jsonb_typeof(p_params) <> 'object'
       or not exists (select 1 from ads_profile_sync where profile_id = p_subject_id) then
        return false;
    end if;
    insert into ai_analysis_settings (module, subject_id, params, updated_by, updated_at)
    values (p_module, p_subject_id, p_params, coalesce(nullif(p_updated_by, ''), 'app'), now())
    on conflict (module, subject_id) do update
       set params = excluded.params, updated_by = excluded.updated_by, updated_at = now()
     where ai_analysis_settings.params is distinct from excluded.params;
    return true;
end;
$$;


create or replace function request_ai_analysis(p_module text, p_subject_id text, p_window_start date,
                                               p_window_end date, p_lang text, p_params jsonb,
                                               p_input_digest text, p_requested_by text)
returns table (job_id bigint, created boolean, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
    profile      ads_profile_sync%rowtype;
    existing_id  bigint;
    local_today  date;
    new_job_id   bigint;
begin
    if not ai_analysis_module_allowed(p_module) or p_lang not in ('es','en') or jsonb_typeof(p_params) <> 'object'
       or coalesce(p_input_digest, '') = '' then
        return query select null::bigint, false, 'invalid_request'::text;
        return;
    end if;

    -- The row lock serializes two people pressing the button for the same account.
    select * into profile from ads_profile_sync where profile_id = p_subject_id for update;
    if not found or profile.status <> 'active' or profile.data_through is null then
        return query select null::bigint, false, 'profile_unavailable'::text;
        return;
    end if;
    if p_window_end < p_window_start or p_window_end > profile.data_through
       or p_window_start < coalesce(profile.data_from, profile.data_through - 59)
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


revoke all on function ai_analysis_module_allowed(text) from public, web_user;
grant execute on function ai_analysis_module_allowed(text) to web_user;

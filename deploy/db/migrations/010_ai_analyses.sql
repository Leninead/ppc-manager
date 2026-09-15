-- 010 — análisis IA guardados y ligados a los datos del reporte.
--
-- El worker de análisis (ads-ai-worker, rol ai_worker) genera el análisis de un reporte cuando llegan
-- datos nuevos por API y lo guarda en ai_analyses, identificado por la huella de lo que lee la IA
-- (input_digest). Si esa huella ya tiene un análisis, no se vuelve a pagar. La app sólo lee: pide un
-- análisis con parámetros nuevos o guarda los parámetros de la cuenta a través de las funciones de abajo,
-- y nunca escribe un resultado, así que nada derivado de un archivo subido a mano llega a la base.
--
-- Los pedidos viajan por integration_sync_jobs (job_kind 'ai_*'), con sus parámetros en la columna params:
-- así heredan reintentos, leases, el Registro de solicitudes y sus alertas. El worker de ingesta deja de
-- reclamarlos y el de análisis reclama sólo esos.

begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'ai_worker') then
    create role ai_worker nologin;
  end if;
end $$;
grant usage on schema public to ai_worker;

alter table integration_sync_jobs add column if not exists params jsonb not null default '{}'::jsonb;
create index if not exists integration_sync_jobs_ai_input_idx
    on integration_sync_jobs (external_account_id, (params->>'input_digest'))
    where job_kind like 'ai\_%';


create table if not exists ai_analysis_settings (
    module      text not null,
    subject_id  text not null,
    params      jsonb not null default '{}'::jsonb,
    updated_by  text not null default '',
    updated_at  timestamptz not null default now(),
    primary key (module, subject_id)
);


create table if not exists ai_analyses (
    id                     bigserial primary key,
    module                 text not null,
    subject_id             text not null,
    window_start           date not null,
    window_end             date not null,
    lang                   text not null check (lang in ('es','en')),
    params                 jsonb not null default '{}'::jsonb,
    params_digest          text not null,
    input_digest           text not null,
    agent_version          text not null,
    status                 text not null default 'running' check (status in ('running','done','failed')),
    trigger                text not null check (trigger in ('scheduled','manual')),
    requested_by           text not null default 'scheduler',
    job_id                 bigint references integration_sync_jobs (id) on delete set null,
    source_last_success_at timestamptz,
    negative_records       jsonb not null default '[]'::jsonb,
    harvest_records        jsonb not null default '[]'::jsonb,
    result                 jsonb,
    session_id             text not null default '',
    request_id             text not null default '',
    model                  text not null default '',
    usage                  jsonb not null default '{}'::jsonb,
    cost_estimate_usd      numeric(10,4),
    duration_ms            integer,
    error_message          text not null default '',
    created_at             timestamptz not null default now(),
    finished_at            timestamptz,
    updated_at             timestamptz not null default now(),
    constraint ai_analyses_window check (window_end >= window_start),
    constraint ai_analyses_once unique (module, subject_id, input_digest, agent_version)
);

create index if not exists ai_analyses_input_idx on ai_analyses (module, subject_id, input_digest);
create index if not exists ai_analyses_history_idx
    on ai_analyses (module, subject_id, finished_at desc) where status = 'done';


-- ── cola: cada worker reclama lo suyo ───────────────────────────────────────

create or replace function claim_sync_jobs(p_holder text, p_limit int, p_lease_seconds int)
returns setof integration_sync_jobs
language sql
as $$
    update integration_sync_jobs job
       set status = 'running',
           lease_holder = p_holder,
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           started_at = coalesce(job.started_at, now()),
           updated_at = now()
      from (
          select id
            from integration_sync_jobs
           where job_kind not like 'ai\_%'
             and ((status in ('pending','retrying') and next_attempt_at <= now() and now() < deadline_at)
                  -- A lapsed lease means the worker died mid-job; every phase resumes safely from its saved chunks.
                  or (status = 'running' and lease_expires_at < now() and now() < deadline_at))
           order by case trigger when 'manual' then 0 when 'retry' then 0 when 'backfill' then 1 else 2 end,
                    next_attempt_at
           limit greatest(p_limit, 0)
           for update skip locked
      ) due
     where job.id = due.id
    returning job.*;
$$;


create or replace function claim_ai_jobs(p_holder text, p_limit int, p_lease_seconds int)
returns setof integration_sync_jobs
language sql
as $$
    update integration_sync_jobs job
       set status = 'running',
           lease_holder = p_holder,
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           started_at = coalesce(job.started_at, now()),
           updated_at = now()
      from (
          select id
            from integration_sync_jobs
           where job_kind like 'ai\_%'
             and ((status in ('pending','retrying') and next_attempt_at <= now() and now() < deadline_at)
                  or (status = 'running' and lease_expires_at < now() and now() < deadline_at))
           order by case trigger when 'manual' then 0 when 'retry' then 0 else 1 end, next_attempt_at
           limit greatest(p_limit, 0)
           for update skip locked
      ) due
     where job.id = due.id
    returning job.*;
$$;


create or replace function retry_sync_job(p_job_id bigint, p_actor text)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
    new_job_id bigint;
begin
    perform 1 from integration_sync_jobs where id = p_job_id for update;

    insert into integration_sync_jobs (
        integration_slug, job_kind, trigger, account_id, connection_id, external_account_id,
        cliente, account_name, marketplace, region, window_start, window_end, local_day,
        status, phase, attempts, max_attempts, next_attempt_at, deadline_at, attempt_log,
        requested_by, retry_of, dedupe_key, params
    )
    select failed_job.integration_slug, failed_job.job_kind, 'retry',
           case when profile.profile_id is null then failed_job.account_id else profile.account_id end,
           case when profile.profile_id is null then failed_job.connection_id else profile.connection_id end,
           failed_job.external_account_id,
           coalesce(nullif(profile.cliente, ''), failed_job.cliente),
           coalesce(nullif(profile.account_name, ''), failed_job.account_name),
           coalesce(nullif(profile.country_code, ''), failed_job.marketplace),
           coalesce(nullif(profile.region, ''), failed_job.region),
           failed_job.window_start, failed_job.window_end, failed_job.local_day, 'pending', '', 0,
           failed_job.max_attempts, now(), now() + interval '6 hours', '[]'::jsonb,
           coalesce(nullif(p_actor, ''), 'app'), failed_job.id, null, failed_job.params
      from integration_sync_jobs failed_job
      -- The failed job may pin an authorization replaced since then: the profile row holds the current one.
      left join ads_profile_sync profile
             on failed_job.integration_slug = 'amazon_ads'
            and profile.profile_id = failed_job.external_account_id
     where failed_job.id = p_job_id
       and failed_job.status in ('failed','cancelled')
       -- Retrying for a missing or disconnected Amazon profile would only queue a job that is sure to fail.
       and (failed_job.integration_slug <> 'amazon_ads' or profile.status = 'active')
       -- A double click must not queue the same retry twice.
       and not exists (
           select 1 from integration_sync_jobs open_retry
            where open_retry.retry_of = failed_job.id
              and open_retry.status in ('pending','running','retrying')
       )
    returning id into new_job_id;

    return new_job_id;
end;
$$;


-- ── lo que la app puede pedir ───────────────────────────────────────────────

create or replace function save_ai_analysis_settings(p_module text, p_subject_id text, p_params jsonb,
                                                     p_updated_by text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_module <> 'str' or jsonb_typeof(p_params) <> 'object'
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
    if p_module <> 'str' or p_lang not in ('es','en') or jsonb_typeof(p_params) <> 'object'
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


-- ── grants ───────────────────────────────────────────────────────────────────
-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla y secuencia nueva,
-- y Postgres da EXECUTE a public sobre toda función nueva.
revoke all on ai_analysis_settings, ai_analyses from web_user;
revoke all on sequence ai_analyses_id_seq from web_user;
revoke all on function claim_sync_jobs(text, int, int),
                       claim_ai_jobs(text, int, int),
                       retry_sync_job(bigint, text),
                       save_ai_analysis_settings(text, text, jsonb, text),
                       request_ai_analysis(text, text, date, date, text, jsonb, text, text)
  from public, web_user;

grant select on ai_analysis_settings, ai_analyses to web_user;
grant execute on function retry_sync_job(bigint, text),
                          save_ai_analysis_settings(text, text, jsonb, text),
                          request_ai_analysis(text, text, date, date, text, jsonb, text, text)
  to web_user;

grant execute on function claim_sync_jobs(text, int, int) to integ_worker;

-- The analysis worker reads the synced search terms and writes only analyses, its jobs and its heartbeat.
grant select on ads_profile_sync, ads_search_term_daily, ads_portfolios, ai_analysis_settings to ai_worker;
grant select, insert, update on integration_sync_jobs, ai_analyses, integration_worker_heartbeats to ai_worker;
grant usage, select on sequence integration_sync_jobs_id_seq, ai_analyses_id_seq to ai_worker;
grant execute on function claim_ai_jobs(text, int, int), search_terms_between(text, date, date) to ai_worker;

commit;

-- PostgREST cachea el esquema: sin esto las tablas y funciones nuevas no existen para él.
notify pgrst, 'reload schema';

-- 009 — sincronización programada de Amazon Ads (Search Term Report).
--
-- integration_sync_jobs es la cola genérica de pedidos a un proveedor: el worker
-- la reclama con lease y deja el rastro de cada intento. Del lado de Amazon viven
-- los reportes pedidos por tramo (ads_report_requests), el estado por perfil
-- (ads_profile_sync), los términos de búsqueda por día (ads_search_term_daily),
-- los nombres de portfolios y el latido del worker. El worker escribe; la app lee
-- y sólo pide, reintenta o cancela a través de las funciones de abajo.

begin;

create table if not exists integration_sync_jobs (
    id                  bigserial primary key,
    integration_slug    text not null,
    job_kind            text not null,
    trigger             text not null
                        check (trigger in ('scheduled_daily','scheduled_deep','backfill','manual','retry')),
    account_id          integer references integration_accounts (id) on delete set null,
    connection_id       integer references integration_connections (id) on delete set null,
    external_account_id text not null default '',
    cliente             text not null default '',
    account_name        text not null default '',
    marketplace         text not null default '',
    region              text not null default '',
    window_start        date,
    window_end          date,
    local_day           date,
    status              text not null default 'pending'
                        check (status in ('pending','running','retrying','completed','failed','cancelled')),
    phase               text not null default ''
                        check (phase in ('','requesting','waiting','saving')),
    attempts            smallint not null default 0,
    max_attempts        smallint not null default 8,
    next_attempt_at     timestamptz not null default now(),
    deadline_at         timestamptz not null,
    lease_holder        text not null default '',
    lease_expires_at    timestamptz,
    rows_written        integer,
    warning             text not null default '',
    error_class         text not null default '',
    error_message       text not null default '',
    attempt_log         jsonb not null default '[]'::jsonb,
    requested_by        text not null default 'scheduler',
    retry_of            bigint references integration_sync_jobs (id) on delete set null,
    dedupe_key          text unique,
    created_at          timestamptz not null default now(),
    started_at          timestamptz,
    finished_at         timestamptz,
    updated_at          timestamptz not null default now(),
    constraint integration_sync_jobs_window check (window_start is null or window_end >= window_start)
);

create index if not exists integration_sync_jobs_due_idx
    on integration_sync_jobs (status, next_attempt_at)
    where status in ('pending','retrying');
create index if not exists integration_sync_jobs_slug_idx
    on integration_sync_jobs (integration_slug, created_at desc);
create index if not exists integration_sync_jobs_account_idx
    on integration_sync_jobs (external_account_id, created_at desc);
alter table integration_sync_jobs set (fillfactor = 70);


create table if not exists ads_report_requests (
    id               bigserial primary key,
    job_id           bigint not null references integration_sync_jobs (id) on delete cascade,
    profile_id       text not null,
    window_start     date not null,
    window_end       date not null,
    status           text not null default 'to_request'
                     check (status in ('to_request','requested','saving','saved','failed')),
    amazon_report_id text not null default '',
    amazon_status    text not null default '',
    requested_at     timestamptz,
    next_poll_at     timestamptz,
    poll_count       integer not null default 0,
    save_attempts    smallint not null default 0,
    lease_holder     text not null default '',
    lease_expires_at timestamptz,
    row_count        integer,
    skipped_days     date[] not null default '{}',
    error_class      text not null default '',
    error_message    text not null default '',
    raw_status       text not null default 'none'
                     check (raw_status in ('none','kept','write_failed','pruned')),
    raw_path         text not null default '',
    raw_bytes        bigint,
    raw_sha256       text not null default '',
    raw_pruned_at    timestamptz,
    saved_at         timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create index if not exists ads_report_requests_poll_idx
    on ads_report_requests (status, next_poll_at);
create index if not exists ads_report_requests_job_idx
    on ads_report_requests (job_id);
create index if not exists ads_report_requests_raw_kept_idx
    on ads_report_requests (raw_status, saved_at)
    where raw_status = 'kept';
alter table ads_report_requests set (fillfactor = 70);


create table if not exists ads_profile_sync (
    profile_id       text primary key,
    account_id       integer references integration_accounts (id) on delete cascade,
    connection_id    integer references integration_connections (id) on delete set null,
    cliente          text not null default '',
    account_name     text not null default '',
    account_type     text not null default '',
    region           text not null default '',
    country_code     text not null default '',
    currency_code    text not null default '',
    timezone         text not null default '',
    access           text not null default '',
    status           text not null default 'active'
                     check (status in ('active','needs_reauth','inactive')),
    backfill_done_at timestamptz,
    data_from        date,
    data_through     date,
    refreshed_on     date,
    last_success_at  timestamptz,
    last_failure_at  timestamptz,
    last_error       text not null default '',
    updated_at       timestamptz not null default now()
);


create table if not exists ads_search_term_daily (
    profile_id        text    not null collate "C",
    report_date       date    not null,
    campaign_id       text    not null collate "C",
    campaign_name     text    not null default '',
    campaign_status   text    not null default '',
    ad_group_id       text    not null collate "C",
    ad_group_name     text    not null default '',
    keyword_type      text    not null default '' collate "C",
    keyword_id        text    not null default '' collate "C",
    keyword_text      text    not null default '',
    match_type        text    not null default '' collate "C",
    targeting         text    not null default '' collate "C",
    ad_keyword_status text    not null default '',
    portfolio_id      text    not null default '',
    search_term       text    not null collate "C",
    impressions       bigint  not null default 0,
    clicks            bigint  not null default 0,
    cost              numeric(14,4) not null default 0,
    purchases_7d      bigint  not null default 0,
    sales_7d          numeric(14,4) not null default 0,
    units_7d          bigint  not null default 0,
    purchases_14d     bigint  not null default 0,
    sales_14d         numeric(14,4) not null default 0,
    units_14d         bigint  not null default 0,
    currency_code     text    not null default '',
    ingested_at       timestamptz not null default now(),
    primary key (profile_id, report_date, campaign_id, ad_group_id, keyword_type,
                 keyword_id, match_type, targeting, search_term)
);
-- Every refresh rewrites whole days, so the default 20% dead-tuple threshold lags far behind.
alter table ads_search_term_daily set (autovacuum_vacuum_scale_factor = 0.02,
                                       autovacuum_analyze_scale_factor = 0.01);
-- search_terms_between reads each campaign's newest row; without this it scans the profile's whole history.
create index if not exists ads_search_term_daily_campaign_state_idx
    on ads_search_term_daily (profile_id, campaign_id, ingested_at desc, report_date desc);


create table if not exists ads_portfolios (
    profile_id   text not null,
    portfolio_id text not null,
    name         text not null default '',
    state        text not null default '',
    seen_at      timestamptz not null default now(),
    primary key (profile_id, portfolio_id)
);


create table if not exists integration_worker_heartbeats (
    worker_name  text primary key,
    last_tick_at timestamptz not null default now(),
    image_tag    text not null default '',
    summary      jsonb not null default '{}'::jsonb
);


-- ── funciones ────────────────────────────────────────────────────────────────

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
           where (status in ('pending','retrying') and next_attempt_at <= now() and now() < deadline_at)
              -- A lapsed lease means the worker died mid-job; every phase resumes safely from its saved chunks.
              or (status = 'running' and lease_expires_at < now() and now() < deadline_at)
           order by case trigger when 'manual' then 0 when 'retry' then 0 when 'backfill' then 1 else 2 end,
                    next_attempt_at
           limit greatest(p_limit, 0)
           for update skip locked
      ) due
     where job.id = due.id
    returning job.*;
$$;


create or replace function claim_report_requests(p_holder text, p_statuses text[], p_limit int, p_lease_seconds int)
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
             and (lease_holder = '' or lease_expires_at is null or lease_expires_at < now())
             and (status <> 'requested' or next_poll_at is null or next_poll_at <= now())
           order by created_at, id
           limit greatest(p_limit, 0)
           for update skip locked
      ) due
     where request.id = due.id
    returning request.*;
$$;


create or replace function replace_search_term_day(p_profile_id text, p_day date, p_rows jsonb)
returns integer
language plpgsql
set statement_timeout = '120s'
as $$
declare
    inserted_count integer;
begin
    -- A null or non-array payload would otherwise fall through to the delete and wipe the day.
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'replace_search_term_day: p_rows must be a json array';
    end if;

    if jsonb_array_length(p_rows) = 0 then
        if exists (select 1 from ads_search_term_daily
                    where profile_id = p_profile_id and report_date = p_day) then
            return -1;
        end if;
        return 0;
    end if;

    delete from ads_search_term_daily where profile_id = p_profile_id and report_date = p_day;

    insert into ads_search_term_daily (
        profile_id, report_date, campaign_id, campaign_name, campaign_status, ad_group_id,
        ad_group_name, keyword_type, keyword_id, keyword_text, match_type, targeting,
        ad_keyword_status, portfolio_id, search_term, impressions, clicks, cost,
        purchases_7d, sales_7d, units_7d, purchases_14d, sales_14d, units_14d, currency_code
    )
    select p_profile_id, p_day, incoming.campaign_id, coalesce(incoming.campaign_name, ''),
           coalesce(incoming.campaign_status, ''), incoming.ad_group_id, coalesce(incoming.ad_group_name, ''),
           coalesce(incoming.keyword_type, ''), coalesce(incoming.keyword_id, ''), coalesce(incoming.keyword_text, ''),
           coalesce(incoming.match_type, ''), coalesce(incoming.targeting, ''), coalesce(incoming.ad_keyword_status, ''),
           coalesce(incoming.portfolio_id, ''), incoming.search_term, coalesce(incoming.impressions, 0),
           coalesce(incoming.clicks, 0), coalesce(incoming.cost, 0), coalesce(incoming.purchases_7d, 0),
           coalesce(incoming.sales_7d, 0), coalesce(incoming.units_7d, 0), coalesce(incoming.purchases_14d, 0),
           coalesce(incoming.sales_14d, 0), coalesce(incoming.units_14d, 0), coalesce(incoming.currency_code, '')
      from jsonb_to_recordset(p_rows) as incoming (
               campaign_id text, campaign_name text, campaign_status text, ad_group_id text,
               ad_group_name text, keyword_type text, keyword_id text, keyword_text text,
               match_type text, targeting text, ad_keyword_status text, portfolio_id text,
               search_term text, impressions bigint, clicks bigint, cost numeric,
               purchases_7d bigint, sales_7d numeric, units_7d bigint, purchases_14d bigint,
               sales_14d numeric, units_14d bigint, currency_code text
           );
    get diagnostics inserted_count = row_count;
    return inserted_count;
end;
$$;


create or replace function search_terms_between(p_profile_id text, p_from date, p_to date)
returns table (
    campaign_id       text,
    ad_group_id       text,
    keyword_type      text,
    keyword_id        text,
    match_type        text,
    targeting         text,
    search_term       text,
    campaign_name     text,
    campaign_status   text,
    ad_group_name     text,
    keyword_text      text,
    ad_keyword_status text,
    portfolio_id      text,
    portfolio_name    text,
    impressions       bigint,
    clicks            bigint,
    cost              numeric,
    purchases_7d      bigint,
    sales_7d          numeric,
    units_7d          bigint,
    purchases_14d     bigint,
    sales_14d         numeric,
    units_14d         bigint,
    currency_code     text
)
language sql
stable
set work_mem = '64MB'
as $$
    with totals as (
        select daily.campaign_id, daily.ad_group_id, daily.keyword_type, daily.keyword_id,
               daily.match_type, daily.targeting, daily.search_term,
               (array_agg(daily.campaign_name     order by daily.report_date desc))[1] as campaign_name,
               (array_agg(daily.ad_group_name     order by daily.report_date desc))[1] as ad_group_name,
               (array_agg(daily.keyword_text      order by daily.report_date desc))[1] as keyword_text,
               (array_agg(daily.ad_keyword_status order by daily.report_date desc))[1] as ad_keyword_status,
               (array_agg(daily.portfolio_id      order by daily.report_date desc))[1] as portfolio_id,
               sum(daily.impressions)::bigint   as impressions,
               sum(daily.clicks)::bigint        as clicks,
               sum(daily.cost)                  as cost,
               sum(daily.purchases_7d)::bigint  as purchases_7d,
               sum(daily.sales_7d)              as sales_7d,
               sum(daily.units_7d)::bigint      as units_7d,
               sum(daily.purchases_14d)::bigint as purchases_14d,
               sum(daily.sales_14d)             as sales_14d,
               sum(daily.units_14d)::bigint     as units_14d,
               max(daily.currency_code)         as currency_code
          from ads_search_term_daily daily
         where daily.profile_id = p_profile_id
           and daily.report_date between p_from and p_to
         group by daily.campaign_id, daily.ad_group_id, daily.keyword_type, daily.keyword_id,
                  daily.match_type, daily.targeting, daily.search_term
    ),
    -- A term's own rows can predate an archive; the campaign's most recently written row carries its current state.
    campaign_state as (
        select campaigns.campaign_id, newest.campaign_status
          from (select distinct totals.campaign_id from totals) campaigns
          cross join lateral (
              select daily.campaign_status
                from ads_search_term_daily daily
               where daily.profile_id = p_profile_id
                 and daily.campaign_id = campaigns.campaign_id
               order by daily.ingested_at desc, daily.report_date desc
               limit 1
          ) newest
    )
    select totals.campaign_id, totals.ad_group_id, totals.keyword_type, totals.keyword_id,
           totals.match_type, totals.targeting, totals.search_term, totals.campaign_name,
           campaign_state.campaign_status, totals.ad_group_name, totals.keyword_text,
           totals.ad_keyword_status, totals.portfolio_id, portfolio.name,
           totals.impressions, totals.clicks, totals.cost, totals.purchases_7d, totals.sales_7d,
           totals.units_7d, totals.purchases_14d, totals.sales_14d, totals.units_14d,
           totals.currency_code
      from totals
      join campaign_state on campaign_state.campaign_id = totals.campaign_id
      left join ads_portfolios portfolio
             on portfolio.profile_id = p_profile_id
            and portfolio.portfolio_id = totals.portfolio_id;
$$;


create or replace function request_manual_refresh(p_profile_id text, p_requested_by text)
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
    -- The row lock serializes two people pressing the button for the same profile.
    select * into profile from ads_profile_sync where profile_id = p_profile_id for update;
    if not found or profile.status <> 'active' then
        return query select null::bigint, false, 'profile_unavailable'::text;
        return;
    end if;

    select open_job.id into existing_id
      from integration_sync_jobs open_job
     where open_job.integration_slug = 'amazon_ads'
       and open_job.job_kind = 'sp_search_terms'
       and open_job.external_account_id = p_profile_id
       and open_job.status in ('pending','running','retrying')
     order by open_job.created_at desc
     limit 1;
    if existing_id is not null then
        return query select existing_id, false, 'already_running'::text;
        return;
    end if;

    select recent_job.id into existing_id
      from integration_sync_jobs recent_job
     where recent_job.integration_slug = 'amazon_ads'
       and recent_job.job_kind = 'sp_search_terms'
       and recent_job.external_account_id = p_profile_id
       and recent_job.trigger = 'manual'
       and recent_job.created_at > now() - interval '30 minutes'
     order by recent_job.created_at desc
     limit 1;
    if existing_id is not null then
        return query select existing_id, false, 'cooldown'::text;
        return;
    end if;

    -- Same fallback as the worker's profile_timezone, so both sides agree on the profile's day.
    local_today := (now() at time zone coalesce(
        nullif(profile.timezone, ''),
        case profile.region when 'EU' then 'Europe/London' when 'FE' then 'Asia/Tokyo'
                            else 'America/Los_Angeles' end
    ))::date;

    insert into integration_sync_jobs (
        integration_slug, job_kind, trigger, account_id, connection_id, external_account_id,
        cliente, account_name, marketplace, region, window_start, window_end, local_day,
        max_attempts, deadline_at, requested_by
    ) values (
        'amazon_ads', 'sp_search_terms', 'manual', profile.account_id, profile.connection_id,
        profile.profile_id, profile.cliente, profile.account_name, profile.country_code,
        profile.region, local_today - 14, local_today - 1, local_today,
        3, now() + interval '6 hours', coalesce(nullif(p_requested_by, ''), 'app')
    )
    returning id into new_job_id;

    return query select new_job_id, true, 'created'::text;
end;
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
        requested_by, retry_of, dedupe_key
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
           coalesce(nullif(p_actor, ''), 'app'), failed_job.id, null
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


create or replace function cancel_sync_job(p_job_id bigint, p_actor text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
    update integration_sync_jobs
       set status = 'cancelled',
           phase = '',
           lease_holder = '',
           lease_expires_at = null,
           finished_at = now(),
           updated_at = now(),
           error_message = 'cancelada por ' || coalesce(nullif(p_actor, ''), 'app')
     where id = p_job_id
       and (status in ('pending','retrying')
            -- A running job whose lease lapsed has no live worker behind it: the admin's way out.
            or (status = 'running' and (lease_expires_at is null or lease_expires_at < now())));
    return found;
end;
$$;


-- ── grants ───────────────────────────────────────────────────────────────────
-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla y secuencia nueva,
-- y Postgres da EXECUTE a public sobre toda función nueva.
revoke all on integration_sync_jobs, ads_report_requests, ads_profile_sync,
              ads_search_term_daily, ads_portfolios, integration_worker_heartbeats
  from web_user;
revoke all on sequence integration_sync_jobs_id_seq, ads_report_requests_id_seq from web_user;
revoke all on function claim_sync_jobs(text, int, int),
                       claim_report_requests(text, text[], int, int),
                       replace_search_term_day(text, date, jsonb),
                       search_terms_between(text, date, date),
                       request_manual_refresh(text, text),
                       retry_sync_job(bigint, text),
                       cancel_sync_job(bigint, text)
  from public, web_user;

grant select on integration_sync_jobs, ads_report_requests, ads_profile_sync,
                ads_search_term_daily, ads_portfolios, integration_worker_heartbeats
  to web_user;
grant execute on function search_terms_between(text, date, date),
                          request_manual_refresh(text, text),
                          retry_sync_job(bigint, text),
                          cancel_sync_job(bigint, text)
  to web_user;

grant select, insert, update on integration_sync_jobs, ads_report_requests, ads_profile_sync,
                                ads_search_term_daily, ads_portfolios, integration_worker_heartbeats
  to integ_worker;
grant delete on ads_search_term_daily, ads_portfolios to integ_worker;
grant usage, select on sequence integration_sync_jobs_id_seq, ads_report_requests_id_seq
  to integ_worker;
grant execute on function claim_sync_jobs(text, int, int),
                          claim_report_requests(text, text[], int, int),
                          replace_search_term_day(text, date, jsonb),
                          search_terms_between(text, date, date)
  to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto las tablas y funciones nuevas no existen para él.
notify pgrst, 'reload schema';

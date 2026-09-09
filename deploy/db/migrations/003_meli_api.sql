-- 003_meli_api.sql — Mercado Libre API tables (roadmap section 9.1 of
-- notes/modules/m36-relevamiento-api-mercado-libre.md).
--
-- Two layers of trust:
--   tier 1  meli_auth_identities         one per seller account. Refresh token
--                                        is SEALED — only integ_worker opens it.
--   tier 2  meli_ingestion_runs, jobs,   worker plumbing: leases, notifications,
--          locks, notifications, ...     retries. The Streamlit app never touches
--                                        these directly.
--
-- Data tables (`_daily`, `_snapshots`) are read-only for web_user through the
-- module's `_load_snapshot` path, which reaches them via the wrapping tables
-- of core/persistence.py — never with direct SELECTs from the module.
--
-- INVARIANT: the app (web_user) can WRITE `refresh_token_sealed` (via portal
-- when a new client authorizes) and NEVER read it back. Same asymmetry as
-- integration_connections in 002_integrations.sql: enforced by the GRANT block,
-- not by a Python role check.
--
-- 002_integrations.sql created `integ_worker`; this migration reuses it: the
-- MELI API worker runs the same process that closes OAuth grants for system
-- credentials, and needs the same sealed-column access.

begin;


-- Per-seller-account identity. One row per user_id returned by MELI's OAuth.
-- Multiple clientes may share a slug and user_id if the same seller works with
-- more than one account manager, so `cliente` is data, not part of the key.
create table if not exists meli_auth_identities (
    id                         serial primary key,
    -- Nickname MELI shows for this account. Human-readable, not stable across
    -- rebrandings; useful for logs and the UI but never a key.
    nickname                   text not null default '',
    -- user_id is stable across renamings and IS the identity from MELI's side.
    -- Unique because a single user_id cannot authorize twice at the same time.
    user_id                    text not null unique,
    site_id                    text not null default 'MLA',
    cliente                    text not null,
    -- Sealed with the public key; only integ_worker opens it. Rotates on
    -- every refresh (MELI's refresh_token is single-use, section 6 of the
    -- relevamiento).
    refresh_token_sealed       text,
    -- Previous generation kept so a crash right after a refresh does not
    -- orphan the account — same pattern as integration_connections.
    refresh_token_prev_sealed  text,
    token_rotated_at           timestamptz,
    access_expires_at          timestamptz,
    refresh_expires_at         timestamptz,
    scopes                     text[] not null default '{}',
    -- Comes from MELI's advertisers endpoint when Product Ads is enabled.
    advertiser_id              text,
    estado                     text not null default 'activo'
                               check (estado in ('activo','needs_reauth','revocado','pausado')),
    last_error                 text not null default '',
    consent_date               date,
    conectado_por              text not null default '',
    metadata                   jsonb not null default '{}'::jsonb,
    created_at                 timestamptz not null default now(),
    updated_at                 timestamptz not null default now()
);
create index if not exists meli_auth_identities_estado_idx
    on meli_auth_identities (estado, cliente);
create index if not exists meli_auth_identities_rotate_idx
    on meli_auth_identities (token_rotated_at) where estado = 'activo';
alter table meli_auth_identities set (fillfactor = 70);


-- One row per worker run, per account. Used for the watchdog (26 h) and
-- for the freshness check in Streamlit (`last successful sync X hours ago`).
create table if not exists meli_ingestion_runs (
    id                    bigserial primary key,
    identity_id           integer not null references meli_auth_identities(id) on delete cascade,
    stage                 text not null,
    started_at            timestamptz not null default now(),
    finished_at           timestamptz,
    status                text not null default 'running'
                          check (status in ('running','ok','error','aborted')),
    requests_made         integer not null default 0,
    rows_written          integer not null default 0,
    error_class           text,
    error_message         text
);
create index if not exists meli_ingestion_runs_identity_started_idx
    on meli_ingestion_runs (identity_id, started_at desc);
create index if not exists meli_ingestion_runs_running_idx
    on meli_ingestion_runs (status, started_at) where status = 'running';


-- Deferred work queue: connect, sync, reingest, revoke. Section 9.1 of the
-- roadmap: the UI never calls MELI in a render — it just enqueues a job and
-- the worker picks it up every 5 minutes.
create table if not exists meli_job_queue (
    id             bigserial primary key,
    identity_id    integer references meli_auth_identities(id) on delete cascade,
    -- `identity_id` nullable because `connect` runs before the identity exists.
    kind           text not null check (kind in ('connect','sync','reingest','revoke')),
    payload        jsonb not null default '{}'::jsonb,
    -- `pending` → `running` (with lease) → `done`/`failed`. `retry` puts it
    -- back to `pending` after clearing the lease.
    status         text not null default 'pending'
                   check (status in ('pending','running','done','failed','cancelled')),
    -- Cooperative lease so two worker processes don't pick the same job.
    lease_holder   text,
    lease_expires  timestamptz,
    attempts       integer not null default 0,
    scheduled_for  timestamptz not null default now(),
    -- Append-only: last error stays visible even when the row moves on.
    last_error     text not null default '',
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists meli_job_queue_pick_idx
    on meli_job_queue (status, scheduled_for) where status = 'pending';
create index if not exists meli_job_queue_identity_idx
    on meli_job_queue (identity_id, kind, status);
alter table meli_job_queue set (fillfactor = 70);


-- Named advisory locks so a single writer owns refresh per user_id, even
-- when two worker processes race. Section 8 of the relevamiento risk matrix.
create table if not exists meli_locks (
    name           text primary key,
    holder         text not null,
    acquired_at    timestamptz not null default now(),
    expires_at     timestamptz not null,
    -- Optional payload to name the operation (a run_id, a job_id).
    context        jsonb not null default '{}'::jsonb
);


-- MELI notification receiver drops the raw body here, ASAP, before doing any
-- work (section 8 of the relevamiento says the endpoint has 500 ms). Real
-- processing happens in a separate reader job that consumes from here.
create table if not exists meli_notifications (
    id             bigserial primary key,
    -- MELI sends the field as `_id` in some topics and `id` in others; the
    -- receiver normalizes to `external_id`.
    external_id    text not null,
    topic          text not null,
    user_id        text not null,
    resource       text,
    application_id text,
    -- Same story as _id/id: `received` vs `recieved` (sic) appear in the
    -- wild; the receiver keeps whichever came.
    sent_at        timestamptz,
    received_at    timestamptz not null default now(),
    body           jsonb not null,
    status         text not null default 'received'
                   check (status in ('received','processed','failed','ignored')),
    processed_at   timestamptz,
    error          text not null default '',
    -- The same notification can come more than once. Dedup by (external_id, topic).
    unique (external_id, topic)
);
create index if not exists meli_notifications_pick_idx
    on meli_notifications (status, received_at) where status = 'received';
create index if not exists meli_notifications_user_topic_idx
    on meli_notifications (user_id, topic, received_at desc);


-- Per-item snapshot fed by inventory + item detail. One row per (mla, day).
-- Section 4.4 of the relevamiento: this is the base for the change tracker's
-- diff against yesterday.
create table if not exists meli_item_snapshots (
    id             bigserial primary key,
    identity_id    integer not null references meli_auth_identities(id) on delete cascade,
    mla            text not null,
    captured_on    date not null,
    -- Denormalized item view. Kept as jsonb because MELI's item shape is
    -- deep (attributes, variations, pictures) and moves per category — a
    -- relational split would need a migration for every category.
    payload        jsonb not null,
    -- Family/user-product ids stay column-level so the tracker survives the
    -- UPtin migration (section 9.3).
    family_id      text,
    user_product_id text,
    unique (identity_id, mla, captured_on)
);
create index if not exists meli_item_snapshots_recent_idx
    on meli_item_snapshots (identity_id, mla, captured_on desc);


-- Daily rendimiento series. Section 9.3 of the relevamiento says the diario
-- table is the SINGLE SOURCE for rendimiento; the 14-day snapshots that the
-- module consumes today are built by `build_snapshot_v1(diario, from, to)`.
-- Kept as separate columns because the module already queries by them.
create table if not exists meli_rendimiento_diario (
    id             bigserial primary key,
    identity_id    integer not null references meli_auth_identities(id) on delete cascade,
    mla            text not null,
    fecha          date not null,
    visitas        integer not null default 0,
    ventas         integer not null default 0,
    unidades       integer not null default 0,
    facturacion    numeric(14,2) not null default 0,
    -- Denormalized to avoid a join on every read from the tracker.
    estado         text,
    titulo         text,
    variantes      integer not null default 1,
    -- true when the sync ran before MELI closed the day (partial data).
    provisorio     boolean not null default false,
    origen         text not null default 'api'
                   check (origen in ('api','excel')),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    unique (identity_id, mla, fecha)
);
create index if not exists meli_rendimiento_diario_mla_fecha_idx
    on meli_rendimiento_diario (identity_id, mla, fecha desc);
alter table meli_rendimiento_diario set (fillfactor = 80);


-- Daily Product Ads series. Section 4.3 of the relevamiento: MELI Ads is now
-- ad-group centric, so campaign_id and ad_group_id are first-class columns.
create table if not exists meli_ads_daily (
    id                bigserial primary key,
    identity_id       integer not null references meli_auth_identities(id) on delete cascade,
    fecha             date not null,
    campaign_id       text not null,
    campaign_name     text not null default '',
    ad_group_id       text not null,
    ad_group_name     text not null default '',
    ad_group_type     text,
    mla               text not null,
    ad_id             text,
    impresiones       integer not null default 0,
    clics             integer not null default 0,
    inversion         numeric(14,2) not null default 0,
    ingresos          numeric(14,2) not null default 0,
    ventas            integer not null default 0,
    unidades          integer not null default 0,
    origen            text not null default 'api'
                      check (origen in ('api','excel')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    -- The primary key includes MLA because a single ad_group can advertise
    -- more than one item (family/catalog groups do).
    unique (identity_id, fecha, campaign_id, ad_group_id, mla)
);
create index if not exists meli_ads_daily_identity_fecha_idx
    on meli_ads_daily (identity_id, fecha desc);
create index if not exists meli_ads_daily_ad_group_idx
    on meli_ads_daily (ad_group_id, fecha desc);
alter table meli_ads_daily set (fillfactor = 80);


-- ── grants ───────────────────────────────────────────────────────────────────
-- schema.sql:143 grants CRUD on tables to web_user by default. Revoke first,
-- then hand back column-scoped writes for the tables the app touches, and
-- leave the ones only the worker sees fully locked from the app.
revoke all on meli_auth_identities, meli_ingestion_runs, meli_job_queue,
              meli_locks, meli_notifications, meli_item_snapshots,
              meli_rendimiento_diario, meli_ads_daily
  from web_user;

-- The app CREATES an identity when a client vendor authorizes (writes the
-- refresh_token_sealed), reads back the public bits, and updates the label.
-- It NEVER reads refresh_token_sealed nor refresh_token_prev_sealed.
grant select (id, nickname, user_id, site_id, cliente, token_rotated_at,
              access_expires_at, refresh_expires_at, scopes, advertiser_id,
              estado, last_error, consent_date, conectado_por, metadata,
              created_at, updated_at)
  on meli_auth_identities to web_user;
grant insert (nickname, user_id, site_id, cliente, refresh_token_sealed,
              scopes, estado, consent_date, conectado_por, metadata)
  on meli_auth_identities to web_user;
grant update (nickname, cliente, advertiser_id, estado, conectado_por, metadata, updated_at)
  on meli_auth_identities to web_user;

-- The app can enqueue jobs (`connect`, `sync`, `reingest`, `revoke`) and read
-- back their status to show progress. It cannot lease or complete them —
-- that's the worker's job.
grant select (id, identity_id, kind, status, attempts, scheduled_for,
              last_error, created_at, updated_at)
  on meli_job_queue to web_user;
grant insert (identity_id, kind, payload, scheduled_for)
  on meli_job_queue to web_user;

-- Ingestion runs and notifications: read-only for the UI (show freshness,
-- show pending notifications). Never writable from the app.
grant select (id, identity_id, stage, started_at, finished_at, status,
              rows_written, error_class)
  on meli_ingestion_runs to web_user;
grant select (id, topic, user_id, received_at, status, processed_at)
  on meli_notifications to web_user;

-- Snapshots and daily series: fully readable, never writable.
grant select on meli_item_snapshots to web_user;
grant select on meli_rendimiento_diario to web_user;
grant select on meli_ads_daily to web_user;

grant usage, select on sequence meli_auth_identities_id_seq,
                                meli_ingestion_runs_id_seq,
                                meli_job_queue_id_seq,
                                meli_notifications_id_seq,
                                meli_item_snapshots_id_seq,
                                meli_rendimiento_diario_id_seq,
                                meli_ads_daily_id_seq
  to web_user;

-- The worker owns all of it: full CRUD across every MELI table.
grant select, insert, update, delete on meli_auth_identities   to integ_worker;
grant select, insert, update, delete on meli_ingestion_runs    to integ_worker;
grant select, insert, update, delete on meli_job_queue         to integ_worker;
grant select, insert, update, delete on meli_locks             to integ_worker;
grant select, insert, update, delete on meli_notifications     to integ_worker;
grant select, insert, update, delete on meli_item_snapshots    to integ_worker;
grant select, insert, update, delete on meli_rendimiento_diario to integ_worker;
grant select, insert, update, delete on meli_ads_daily         to integ_worker;
grant usage, select on sequence meli_auth_identities_id_seq,
                                meli_ingestion_runs_id_seq,
                                meli_job_queue_id_seq,
                                meli_notifications_id_seq,
                                meli_item_snapshots_id_seq,
                                meli_rendimiento_diario_id_seq,
                                meli_ads_daily_id_seq
  to integ_worker;

commit;

-- PostgREST caches the schema; without this, the new tables do not exist for it.
notify pgrst, 'reload schema';

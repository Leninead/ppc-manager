-- Agency OS — self-hosted Postgres schema for the PostgREST substitute.
-- Reconstructed from the app's persistence layer (the app talks pure PostgREST, no SQL).
-- Config A: one CRUD role, no RLS, no JWT — matches the single-tenant prod posture.
-- Loaded once by the postgres image on first init (/docker-entrypoint-initdb.d).

create extension if not exists pgcrypto;  -- gen_random_uuid() for innovation tables

-- Auth: PostgREST verifies the app's JWT (PGRST_JWT_SECRET) and switches to the role in its
-- `role` claim. web_user carries CRUD; web_anon (the no-token anon role) has no privileges, so
-- any request without a valid signed token is denied.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'web_anon') then create role web_anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'web_user') then create role web_user nologin; end if;
end $$;
grant usage on schema public to web_user;

-- ── Account Health (core/persistence.py) ────────────────────────────────────
-- data is TEXT here on purpose: df.to_json(orient="table") round-tripped via pd.read_json.
create table if not exists ah_snapshots (
    area     text    not null,
    cliente  text    not null,
    modulo   text    not null,
    period   text    not null,
    data     text    not null,
    primary key (area, cliente, modulo, period)
);

create table if not exists ah_configs (
    area     text    not null,
    modulo   text    not null,
    name     text    not null,
    version  integer not null,
    data     jsonb   not null,
    primary key (area, modulo, name, version)
);

-- Append-only log. id is bigserial (NOT uuid): reads order by id.asc to keep insertion order.
create table if not exists ah_logs (
    id         bigserial   primary key,
    area       text        not null,
    cliente    text        not null,
    modulo     text        not null,
    log_name   text        not null,
    data       jsonb       not null,
    created_at timestamptz not null default now()
);

create table if not exists ah_client_configs (
    area     text  not null,
    cliente  text  not null,
    modulo   text  not null,
    name     text  not null,
    data     jsonb not null,
    primary key (area, cliente, modulo, name)
);

-- ── Revenue Forecast (core/forecast/persistence.py) ─────────────────────────
create table if not exists forecast_clients (
    area     text  not null,
    cliente  text  not null,
    modulo   text  not null,
    name     text  not null,
    data     jsonb not null,
    primary key (area, cliente, modulo, name)
);

-- ── Sales Proposals (core/proposal_persistence.py) ──────────────────────────
create table if not exists proposals (
    id          text    not null,
    version     integer not null,
    client_name text,
    status      text,
    archetype   text,
    updated_at  text,
    data        jsonb   not null,
    primary key (id, version)
);
create index if not exists proposals_id_idx on proposals (id);

create table if not exists proposal_votes (
    id          text primary key,
    module_id   text not null,
    voter_name  text,
    voted_at    text,
    proposal_id text
);

-- ── Innovation Board (core/innovation/persistence.py) — from m24 DDL, RLS dropped ──
create table if not exists innovation_ideas (
    id                uuid primary key default gen_random_uuid(),
    titulo            text        not null,
    descripcion       text        not null default '',
    problema          text        not null default '',
    area              text        not null default 'ops',
    impacto           text        not null default 'medio',
    esfuerzo          text        not null default 'medio',
    modulo_destino    text        not null default '',
    autor             text        not null default '',
    estado            text        not null default 'nueva',
    asignado_a        text        not null default '',
    razon_descarte    text        not null default '',
    estado_updated_at timestamptz not null default now(),
    created_at        timestamptz not null default now()
);
create index if not exists idx_innovation_ideas_area_estado on innovation_ideas (area, estado);

create table if not exists innovation_votos (
    id         uuid primary key default gen_random_uuid(),
    idea_id    uuid        not null references innovation_ideas (id) on delete cascade,
    votante    text        not null,
    valor      integer     not null default 0,
    razon      text        not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_innovation_votos_idea_votante unique (idea_id, votante)
);
create index if not exists idx_innovation_votos_idea on innovation_votos (idea_id);

create table if not exists innovation_comentarios (
    id         uuid primary key default gen_random_uuid(),
    idea_id    uuid        not null references innovation_ideas (id) on delete cascade,
    autor      text        not null default '',
    cuerpo     text        not null default '',
    destacado  boolean     not null default false,
    created_at timestamptz not null default now()
);
create index if not exists idx_innovation_comentarios_idea on innovation_comentarios (idea_id);

create table if not exists innovation_prototipos (
    id           uuid primary key default gen_random_uuid(),
    idea_id      uuid        not null references innovation_ideas (id) on delete cascade,
    nombre       text        not null,
    version      integer     not null default 1,
    html_content text        not null default '',
    autor        text        not null default '',
    created_at   timestamptz not null default now()
);
create index if not exists idx_innovation_prototipos_idea on innovation_prototipos (idea_id);

-- ── Grants to web_user (tables exist now) + defaults for anything created later ─────────
grant select, insert, update, delete on all tables in schema public to web_user;
grant usage, select on all sequences in schema public to web_user;
alter default privileges in schema public grant select, insert, update, delete on tables to web_user;
alter default privileges in schema public grant usage, select on sequences to web_user;

-- ============================================================================
-- M24 Innovation Board — schema Supabase (PostgreSQL)
-- ----------------------------------------------------------------------------
-- Ejecutar UNA vez en Supabase ANTES de encender el backend remoto
-- (AGENCY_OS_INNOVATION_BACKEND="supabase"). Espeja el layout local de
-- core/innovation_persistence.py.
--
-- NO ejecutado automáticamente por ningún proceso — es el DDL de swap-day.
-- Idempotente: usa "create ... if not exists" y "on conflict do nothing".
--
-- RLS: ACTIVADA en las 4 tablas, con policy permisiva para service_role.
--      El backend usa la service key (server-side, sin usuarios finales), así
--      que service_role tiene acceso total. NO se deja RLS off.
-- ============================================================================

-- ── Tabla madre: ideas ──────────────────────────────────────────────────────
create table if not exists innovation_ideas (
    id             uuid primary key default gen_random_uuid(),
    titulo         text        not null,
    descripcion    text        not null default '',
    problema       text        not null default '',
    area           text        not null default 'ops',
    impacto        text        not null default 'medio',   -- alto | medio | bajo
    esfuerzo       text        not null default 'medio',   -- alto | medio | bajo
    modulo_destino text        not null default '',
    autor          text        not null default '',
    estado         text        not null default 'nueva',
    created_at     timestamptz not null default now()
);

create index if not exists idx_innovation_ideas_area_estado
    on innovation_ideas (area, estado);

-- ── Hija: votos (1 voto por persona por idea) ───────────────────────────────
create table if not exists innovation_votos (
    id         uuid primary key default gen_random_uuid(),
    idea_id    uuid        not null references innovation_ideas (id) on delete cascade,
    votante    text        not null,
    valor      integer     not null default 0,             -- -1 | 0 | 1
    razon      text        not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_innovation_votos_idea_votante unique (idea_id, votante)
);

create index if not exists idx_innovation_votos_idea
    on innovation_votos (idea_id);

-- ── Hija: comentarios ───────────────────────────────────────────────────────
create table if not exists innovation_comentarios (
    id         uuid primary key default gen_random_uuid(),
    idea_id    uuid        not null references innovation_ideas (id) on delete cascade,
    autor      text        not null default '',
    cuerpo     text        not null default '',
    destacado  boolean     not null default false,
    created_at timestamptz not null default now()
);

create index if not exists idx_innovation_comentarios_idea
    on innovation_comentarios (idea_id);

-- ── Hija: prototipos (versionados por (idea_id, nombre)) ─────────────────────
create table if not exists innovation_prototipos (
    id           uuid primary key default gen_random_uuid(),
    idea_id      uuid        not null references innovation_ideas (id) on delete cascade,
    nombre       text        not null,
    version      integer     not null default 1,
    html_content text        not null default '',
    autor        text        not null default '',
    created_at   timestamptz not null default now()
);

create index if not exists idx_innovation_prototipos_idea
    on innovation_prototipos (idea_id);

-- ============================================================================
-- Row Level Security — ACTIVADA + policy permisiva para service_role
-- ============================================================================
alter table innovation_ideas       enable row level security;
alter table innovation_votos       enable row level security;
alter table innovation_comentarios enable row level security;
alter table innovation_prototipos  enable row level security;

-- El backend server-side usa la service key → service_role acceso total.
-- Se crean con guard para que el script sea re-ejecutable sin error.
do $$
begin
    if not exists (
        select 1 from pg_policies
        where tablename = 'innovation_ideas' and policyname = 'service_role_all'
    ) then
        create policy service_role_all on innovation_ideas
            for all to service_role using (true) with check (true);
    end if;

    if not exists (
        select 1 from pg_policies
        where tablename = 'innovation_votos' and policyname = 'service_role_all'
    ) then
        create policy service_role_all on innovation_votos
            for all to service_role using (true) with check (true);
    end if;

    if not exists (
        select 1 from pg_policies
        where tablename = 'innovation_comentarios' and policyname = 'service_role_all'
    ) then
        create policy service_role_all on innovation_comentarios
            for all to service_role using (true) with check (true);
    end if;

    if not exists (
        select 1 from pg_policies
        where tablename = 'innovation_prototipos' and policyname = 'service_role_all'
    ) then
        create policy service_role_all on innovation_prototipos
            for all to service_role using (true) with check (true);
    end if;
end $$;

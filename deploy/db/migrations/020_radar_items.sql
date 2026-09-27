-- 020 — Radar Amazon: los temas de la semana que leyó y resumió la IA desde los feeds de referentes y de Amazon.
--
-- Una corrida (python -m core.radar.run) lee los feeds, se queda con los items fechados dentro de los últimos 7 días
-- cuyo link responde, le pide a la IA que los agrupe por tema y guarda un tema por fila. La confianza no la decide la
-- IA: la calcula el código a partir de las fuentes. Escribe el rol del worker de análisis (ai_worker), que ya habla con
-- el AI provider; la app sólo lee.
--
-- Correr dos veces la misma semana reescribe sus temas (unique week_start + primary_link); created_at es el momento
-- de la corrida que escribió la fila, compartido por todas las filas de esa corrida.

begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'ai_worker') then
    create role ai_worker nologin;
  end if;
end $$;
grant usage on schema public to ai_worker;


create table if not exists radar_items (
    id                    bigserial primary key,
    week_start            date not null,
    title_es              text not null,
    summary_es            text not null,
    implications_es       text not null,
    confidence            text not null check (confidence in ('official', 'confirmed', 'expert')),
    -- [{source_id, name, person, title, link, published_at, verified_at, http_status, is_official}]
    sources               jsonb not null default '[]'::jsonb check (jsonb_typeof(sources) = 'array'),
    primary_link          text not null,
    primary_published_at  timestamptz not null,
    rank                  int not null check (rank >= 1),
    input_digest          text not null default '',
    agent_version         text not null default '',
    model                 text not null default '',
    usage                 jsonb not null default '{}'::jsonb,
    created_at            timestamptz not null default now(),
    unique (week_start, primary_link)
);

create index if not exists radar_items_latest_idx on radar_items (week_start desc, created_at desc);


-- ── grants ───────────────────────────────────────────────────────────────────
-- Revocar primero: schema.sql da CRUD a web_user sobre toda tabla y secuencia nueva.
revoke all on radar_items from web_user;
revoke all on sequence radar_items_id_seq from web_user;

grant select on radar_items to web_user;

-- Upsert = insert + update; select lo pide PostgREST para resolver el conflicto.
grant select, insert, update on radar_items to ai_worker;
grant usage, select on sequence radar_items_id_seq to ai_worker;

commit;

-- PostgREST caches the schema: without this the new table answers 404 until it restarts.
notify pgrst, 'reload schema';

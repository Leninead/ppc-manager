-- 002_integrations.sql — portal de Integraciones. Dos niveles de credencial:
--   tier 1  integration_credentials   una por integración. La rompe un admin, la sufren todos.
--   tier 2  integration_connections   N por integración, una por cuenta de cliente.
--
-- INVARIANTE: la app (web_user) puede ESCRIBIR material sellado y NUNCA leerlo.
-- No lo garantiza el chequeo de rol en Python — AGENCY_OS_LOCAL_MODE (app.py:166)
-- puentea el login entero. Lo garantiza el GRANT por columna del bloque final.
-- Simplificar esos grants a `grant select on … to web_user` borra la propiedad
-- en silencio: sin error y sin test que falle.
--
-- 001 queda reservado para la migración de Amazon Ads, que vive sin mergear en
-- feat/ads-api-str-ingestion.

begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'integ_worker') then
    create role integ_worker nologin;
  end if;
end $$;
grant usage on schema public to integ_worker;


-- Configuración del portal que no es secreta: hoy, la clave PÚBLICA de sellado.
-- Vive en la base y no en una variable de entorno para que un admin pueda
-- generarla desde la pantalla, que es el punto del portal.
create table if not exists integration_settings (
    clave      text primary key,
    valor      text not null,
    updated_by text not null default '',
    updated_at timestamptz not null default now()
);


create table if not exists integration_credentials (
    id                serial primary key,
    integration_slug  text not null,
    label             text not null default '',
    -- Mitad pública: el client_id no es secreto y la app TIENE que leerlo para
    -- armar la URL de consentimiento. Esa asimetría es la que fuerza el split.
    public_fields     jsonb not null default '{}'::jsonb,
    -- Clase app_readable: la consume el propio proceso de Streamlit.
    secret_app        text,
    -- Clase sealed: RSA-OAEP con la clave pública. Sólo el worker la abre.
    secret_sealed     text,
    fingerprint       text not null default '',
    estado            text not null default 'activo'
                      check (estado in ('activo','invalido')),
    created_by        text not null default '',
    rotated_by        text not null default '',
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

-- Una sola credencial activa por integración; el histórico queda como rastro.
create unique index if not exists integration_credentials_activa_idx
    on integration_credentials (integration_slug)
    where estado = 'activo';


create table if not exists integration_connections (
    id                   serial primary key,
    integration_slug     text not null,
    cliente              text not null,
    cuenta_externa_id    text not null,
    nombre_externo       text not null default '',
    marketplace          text not null default '',
    -- El refresh de Mercado Libre es de un solo uso y rota en cada llamada.
    -- prev_* da una generación de gracia: si el worker muere entre refrescar y
    -- persistir, la cuenta se recupera en vez de morir.
    refresh_token_sealed      text,
    refresh_token_prev_sealed text,
    token_rotated_at     timestamptz,
    access_expires_at    timestamptz,
    scopes               text[],
    estado               text not null default 'activo'
                         check (estado in ('activo','pausado','needs_reauth','revocado')),
    consent_date         date,
    last_sync_at         timestamptz,
    last_error           text not null default '',
    conectado_por        text not null default '',
    metadata             jsonb not null default '{}'::jsonb,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    -- Sin `cliente` a propósito: una misma cuenta de vendedor no puede quedar
    -- reclamada por dos clientes distintos.
    unique (integration_slug, cuenta_externa_id)
);

create index if not exists integration_connections_slug_idx
    on integration_connections (integration_slug, estado);
create index if not exists integration_connections_cliente_idx
    on integration_connections (cliente);
alter table integration_connections set (fillfactor = 70);


-- Autorización en vuelo. La FILA es el estado, no la pestaña del navegador:
-- el usuario puede cerrar el diálogo, cambiar de pestaña o perder la sesión y
-- el flujo sigue siendo correcto.
create table if not exists integration_pending_grants (
    id                serial primary key,
    integration_slug  text not null,
    cliente           text not null,
    marketplace       text not null default '',
    state             text not null unique,
    verifier_sealed   text not null,
    code_sealed       text,
    estado            text not null default 'pendiente'
                      check (estado in ('pendiente','recibido','canjeado','fallido','vencido')),
    error             text not null default '',
    solicitado_por    text not null default '',
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index if not exists integration_pending_grants_abiertos_idx
    on integration_pending_grants (estado, created_at);


-- Append-only por GRANT: nadie tiene update ni delete.
create table if not exists integration_audit (
    id               bigserial primary key,
    actor            text not null,
    accion           text not null,
    integration_slug text,
    resultado        text not null default 'ok'
                     check (resultado in ('ok','error','denegado')),
    detalle          jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now(),
    -- Defensa en profundidad: que un descuido no meta material sensible acá.
    constraint integration_audit_sin_secretos check (
        not (detalle ?| array['secret','token','api_key','client_secret',
                              'password','refresh_token','verifier'])
    )
);

create index if not exists integration_audit_slug_idx
    on integration_audit (integration_slug, created_at desc);


-- ── grants ───────────────────────────────────────────────────────────────────
-- Revocar es OBLIGATORIO y va primero: schema.sql:143 hace
--   alter default privileges in schema public grant select, insert, update, delete
--   on tables to web_user;
-- así que estas cuatro tablas NACEN con CRUD completo para la app, incluido
-- SELECT sobre las columnas selladas.
revoke all on integration_settings, integration_credentials,
              integration_connections, integration_pending_grants, integration_audit
  from web_user;

-- Nada secreto acá: la clave pública sella y no abre.
grant select, insert, update on integration_settings to web_user;

-- tier 1 — escribir sin poder leer: secret_sealed está en INSERT y en UPDATE,
-- y ausente del SELECT. secret_app sí se lee: lo consume la propia app.
grant select (id, integration_slug, label, public_fields, secret_app, fingerprint,
              estado, created_by, rotated_by, created_at, updated_at)
  on integration_credentials to web_user;
grant insert (integration_slug, label, public_fields, secret_app, secret_sealed,
              fingerprint, estado, created_by)
  on integration_credentials to web_user;
grant update (label, public_fields, secret_app, secret_sealed, fingerprint,
              estado, rotated_by, updated_at)
  on integration_credentials to web_user;

-- tier 2 — asimetría deliberada: la app puede CREAR una autorización pero no
-- rotar su token. refresh_token_sealed está en INSERT y ausente del UPDATE.
grant select (id, integration_slug, cliente, cuenta_externa_id, nombre_externo,
              marketplace, token_rotated_at, access_expires_at, scopes, estado,
              consent_date, last_sync_at, last_error, conectado_por, metadata,
              created_at, updated_at)
  on integration_connections to web_user;
grant insert (integration_slug, cliente, cuenta_externa_id, nombre_externo,
              marketplace, refresh_token_sealed, scopes, estado, consent_date,
              conectado_por, metadata)
  on integration_connections to web_user;
grant update (nombre_externo, marketplace, estado, conectado_por, metadata, updated_at)
  on integration_connections to web_user;

-- El verifier y el code se sellan con la pública: la app los escribe y no los abre.
grant select (id, integration_slug, cliente, marketplace, state, estado, error,
              solicitado_por, created_at, updated_at)
  on integration_pending_grants to web_user;
grant insert (integration_slug, cliente, marketplace, state, verifier_sealed,
              estado, solicitado_por)
  on integration_pending_grants to web_user;
grant update (code_sealed, estado, updated_at)
  on integration_pending_grants to web_user;

grant select, insert on integration_audit to web_user;

grant usage, select on sequence integration_credentials_id_seq,
                                integration_connections_id_seq,
                                integration_pending_grants_id_seq,
                                integration_audit_id_seq
  to web_user;

-- El worker es el único que abre material sellado.
-- El worker publica la clave publica de sellado en su primer `worker keys`.
grant select, insert, update on integration_settings to integ_worker;
grant select, insert, update, delete on integration_credentials      to integ_worker;
grant select, insert, update, delete on integration_connections      to integ_worker;
grant select, insert, update, delete on integration_pending_grants   to integ_worker;
grant select, insert on integration_audit to integ_worker;
grant usage, select on sequence integration_credentials_id_seq,
                                integration_connections_id_seq,
                                integration_pending_grants_id_seq,
                                integration_audit_id_seq
  to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto las tablas nuevas no existen para él.
notify pgrst, 'reload schema';

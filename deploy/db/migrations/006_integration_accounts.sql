-- 006 — cuentas de clientes descubiertas por una autorización.
--
-- Amazon Ads separa dos cosas que en Mercado Libre coinciden. En Mercado Libre
-- el vendedor autoriza su propia cuenta: la fila de `integration_connections`
-- es la autorización Y la cuenta del cliente. En Amazon quien autoriza es un
-- empleado de Capybaras con su usuario de Amazon, al que cada cliente invitó a
-- su cuenta: una autorización alcanza N cuentas de clientes, y el mismo cliente
-- puede verse desde dos empleados. Meter las dos ideas en la misma tabla
-- obligaba a duplicar el token del empleado por cada cliente.
--
-- Acá vive la cuenta del cliente: una por (proveedor, id de entidad de Amazon),
-- con la región (el host de la API al que pertenece), sus países, el tipo, la
-- etiqueta `cliente` que la agencia puede corregir, y qué autorización la vio
-- por última vez. El worker escribe; la app lee y sólo puede editar la
-- etiqueta. `first_seen_at` / `last_seen_at` son hechos, no estados: una cuenta
-- que dejó de verse no se borra sola.

begin;

create table if not exists integration_accounts (
    id                 serial primary key,
    integration_slug   text not null,
    cuenta_externa_id  text not null,
    nombre_externo     text not null default '',
    tipo               text not null default '',
    region             text not null default '',
    marketplaces       text[] not null default '{}',
    cliente            text not null default '',
    connection_id      integer references integration_connections (id) on delete set null,
    profiles           jsonb not null default '[]'::jsonb,
    first_seen_at      timestamptz not null default now(),
    last_seen_at       timestamptz not null default now(),
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    unique (integration_slug, cuenta_externa_id)
);

create index if not exists integration_accounts_slug_idx
    on integration_accounts (integration_slug);
create index if not exists integration_accounts_connection_idx
    on integration_accounts (connection_id);
create index if not exists integration_accounts_cliente_idx
    on integration_accounts (cliente);

-- ── grants ───────────────────────────────────────────────────────────────────
-- Revocar primero: schema.sql da CRUD completo a web_user sobre toda tabla nueva.
revoke all on integration_accounts from web_user;

-- Nada sellado acá. La app lee todo y sólo corrige la etiqueta.
grant select on integration_accounts to web_user;
grant update (cliente, updated_at) on integration_accounts to web_user;

grant select, insert, update, delete on integration_accounts to integ_worker;
grant usage, select on sequence integration_accounts_id_seq to integ_worker;

commit;

-- PostgREST cachea el esquema: sin esto la tabla nueva no existe para él.
notify pgrst, 'reload schema';

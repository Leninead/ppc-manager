-- 008 — rol `integ_provider`: el AI provider lee el portal por su cuenta.
--
-- Los chats de la app (STR, SQP, DataDive) pueden consultar el MCP oficial de
-- Amazon Ads sobre la cuenta de cliente que el AM elige en la barra lateral.
-- Quien abre esa sesión no es la app sino capybaras-ai-provider, y para eso
-- necesita, por sí mismo, tres cosas del portal: la cuenta (fila de
-- integration_accounts y su perfil), la autorización que la sostiene (el
-- refresh token sellado del empleado) y la credencial de sistema (client_id
-- público + client_secret sellado). La app sigue sin poder leer nada sellado:
-- web_user no cambia.
--
-- Un rol propio, y no el del worker, porque el provider necesita MENOS: ni
-- pending_grants, ni settings, ni borrar, ni crear. Lo único que escribe es
-- (a) marcar `needs_reauth` la autorización cuando Login with Amazon dice que
-- el grant murió, para que la pantalla deje de llamarla activa, y (b) una fila
-- de auditoría por turno de chat con herramientas. El JWT del rol se acuña con
-- `sh scripts/mint_jwt.sh integ_provider` y vive sólo en el .env del provider.

begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'integ_provider') then
    create role integ_provider nologin;
  end if;
end $$;
grant usage on schema public to integ_provider;

-- La cuenta del cliente: qué perfiles tiene y de qué autorización cuelga.
grant select (id, integration_slug, cliente, nombre_externo, region, profiles, connection_id)
  on integration_accounts to integ_provider;

-- La autorización: sólo lo que hace falta para refrescar y para informar quién
-- la dio. Sin prev_*, sin scopes, sin metadata.
grant select (id, integration_slug, cliente, cuenta_externa_id, estado, conectado_por,
              refresh_token_sealed, consent_date)
  on integration_connections to integ_provider;
grant update (estado, last_error, updated_at)
  on integration_connections to integ_provider;

-- La credencial de sistema: el client_id está en public_fields, el secret sellado.
grant select (integration_slug, public_fields, secret_sealed, estado)
  on integration_credentials to integ_provider;

-- Auditoría: una fila por turno con herramientas (cuenta, perfil, qué tools
-- corrieron; nunca argumentos ni respuestas).
grant insert on integration_audit to integ_provider;
grant usage, select on sequence integration_audit_id_seq to integ_provider;

commit;

-- PostgREST cachea los roles y sus permisos: sin esto el JWT nuevo responde 401/403.
notify pgrst, 'reload schema';

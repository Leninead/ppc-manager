-- 007 — el receptor puede dejar escrito por qué falló un consentimiento.
--
-- Cuando la persona cancela en la pantalla del proveedor, o la app está mal
-- configurada (`invalid_scope`, `unauthorized_client`), el proveedor vuelve al
-- callback con `error` y el `state`. El receptor marca el grant como
-- `fallido` con ese texto para que la falla sea visible en la auditoría y no
-- sólo en la pestaña que la persona acaba de cerrar. 002 le dio a web_user
-- UPDATE sobre `code_sealed`, `estado` y `updated_at` únicamente, así que la
-- escritura del texto respondía 403 y la fila quedaba `pendiente` hasta vencer.

begin;

grant update (error) on integration_pending_grants to web_user;

commit;

notify pgrst, 'reload schema';

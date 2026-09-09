-- 005 — let the receiver persist MELI webhooks.
--
-- 003 granted web_user select-only on meli_notifications, but the receiver
-- runs as web_user (INTEGRATIONS_RECEIVER_JWT, role=web_user) and inserts
-- every incoming webhook. The result was silent data loss: PostgREST answered
-- 403, the receiver logged it and still returned 200 to MELI (correct — a
-- retry storm would not help), so notifications were dropped with no alert.
--
-- The grant is column-scoped and covers exactly what the receiver writes.
-- `status`, `processed_at` and `error` stay out: only the worker moves a
-- notification out of 'received'.
grant insert (external_id, topic, user_id, resource, application_id,
              sent_at, body)
  on meli_notifications to web_user;

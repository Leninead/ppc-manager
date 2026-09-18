-- 016 — every turn of the app's chat, kept for later reading.
--
-- The app writes one row per finished turn and can never read, change or delete them: the rows hold
-- client data and what each AM asked. They are read with SQL on the VPS.

begin;

create table if not exists chat_turns (
    id              bigserial primary key,
    created_at      timestamptz not null default now(),
    conversation_id uuid not null,
    username        text not null,
    page            text not null,
    ads_profile_id  text,
    ads_account     text,
    question        text not null,
    answer          text,
    error           text,
    tools           text[] not null default '{}',
    model           text,
    cost_usd        numeric(12, 6),
    constraint chat_turns_answer_or_error check ((answer is null) <> (error is null))
);

comment on column chat_turns.created_at is
    'When the turn finished.';
comment on column chat_turns.conversation_id is
    'Shared by every turn of one browser session: the thread the AM saw.';
comment on column chat_turns.page is
    'Routing key of the page the AM asked from, the same in every language.';
comment on column chat_turns.ads_profile_id is
    'Amazon Ads profile loaded on that page, if any. The question may be about another account.';
comment on column chat_turns.ads_account is
    'Label of that account, as the page showed it.';
comment on column chat_turns.answer is
    'What the AM read; a chart is kept as its text. Null when the turn failed.';
comment on column chat_turns.error is
    'The error the AM read when the turn failed. Null when it was answered.';
comment on column chat_turns.tools is
    'Tools the model called, in order, by their provider names.';
comment on column chat_turns.model is
    'Model the app asked for. A provider fallback to another model is not visible here.';
comment on column chat_turns.cost_usd is
    'Cost the provider reports, estimated at API prices.';

-- schema.sql grants web_user CRUD on every new table and sequence: take it all back first.
revoke all on chat_turns from web_user;
revoke all on sequence chat_turns_id_seq from web_user;

grant insert (conversation_id, username, page, ads_profile_id, ads_account, question, answer, error,
              tools, model, cost_usd)
  on chat_turns to web_user;
grant usage on sequence chat_turns_id_seq to web_user;

commit;

-- PostgREST caches the schema: without this the new table answers 404 until it restarts.
notify pgrst, 'reload schema';

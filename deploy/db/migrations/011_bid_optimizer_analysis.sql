-- Bid Optimizer analyses reuse ai_analyses (migration 010): its module column already separates
-- them from the Search Term Report's, and claim_ai_jobs claims any 'ai\_%' job kind.
--
-- What they do not have is somewhere to keep the rows the analysis was built from. M2 stores its
-- two lists in negative_records / harvest_records; naming a module's rows after M2's candidates
-- would only work for M2, so the generic column holds them for every module that comes after.

alter table ai_analyses
    add column if not exists records jsonb not null default '[]'::jsonb;

comment on column ai_analyses.records is
    'Rows the analysis was built from, in the order their row_ids were given. Modules other than str.';

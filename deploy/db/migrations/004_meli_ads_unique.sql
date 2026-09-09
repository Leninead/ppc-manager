-- 004_meli_ads_unique.sql — Support upserts against meli_ads_daily using the
-- 4-column key (identity_id, fecha, campaign_id, ad_group_id).
--
-- Rationale
-- ---------
-- 003_meli_api.sql creates the meli_ads_daily table with a 5-column UNIQUE
-- constraint that includes `mla`. That constraint is the right shape for
-- Excel imports, which land one row per advertised item.
--
-- The API ingest works a level up: it pulls aggregated metrics per date at
-- the campaign level (ad_group_id sentinel 'ALL') and per date at each
-- ad_group. It has no MLA at that granularity — everything is rolled up.
-- To upsert those rows we need PostgREST to see a unique index on the
-- 4-column key it can point on_conflict at.
--
-- Compatibility
-- -------------
-- The 5-column UNIQUE from 003 stays in place. Per-item Excel rows keep
-- upserting on the wider key. The 4-column index below is a subset that
-- only ever sees API rows, which never carry a per-item MLA.
--
-- Idempotent: `if not exists` makes reruns a no-op.

begin;

create unique index if not exists meli_ads_daily_ident_date_camp_grp_idx
    on meli_ads_daily (identity_id, fecha, campaign_id, ad_group_id);

commit;

-- 022 — The PPC Insights analysis worker reads the account's Sponsored Products listing.
--
-- Additive, grants only. PPC Insights scores each ASIN's campaigns from the SP listing (sp_structure_between, 018),
-- the page and the stored analysis alike: without these grants the worker could not rebuild the digest the page asks
-- for. The function runs with its caller's permissions, and Postgres checks every table it names, also those of the
-- families a call does not ask for. ads_campaign, ads_campaign_daily, ads_product_ad and ads_portfolios were already
-- granted (010, 014, 017).

begin;

grant select on ads_ad_group, ads_target, ads_target_daily, ads_target_bid, ads_negative, ads_listing_snapshot
  to ai_worker;
grant execute on function sp_structure_between(text, date, date, text[], text[]) to ai_worker;

commit;

-- Reload PostgREST's schema cache, as every migration does.
notify pgrst, 'reload schema';

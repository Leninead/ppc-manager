"""Read-only DB smoke: confirm the self-hosted PostgREST answers for every table.
Run inside the app container. No writes (safe on prod). Skips if the DB backend is off.
"""
import os
import sys
import urllib.error
import urllib.request

# `--require` turns the skip into a failure. The caller passes it when the
# deployment does have the db overlay: without it, a stack that silently lost
# the overlay would exit 0 here and the pipeline would report a green DB gate
# over a database nobody checked.
required = "--require" in sys.argv

base = os.environ.get("SUPABASE_URL")
if not base:
    if required:
        print("SUPABASE_URL is unset but the deployment declares the DB overlay.")
        sys.exit(1)
    print("DB backend not active (no SUPABASE_URL) — skipping DB smoke.")
    sys.exit(0)
key = os.environ.get("SUPABASE_KEY", "")  # the JWT PostgREST verifies; sent as the app does

# (table, select). `*` for tables web_user may read whole; an explicit column
# for the ones under column-level GRANTs — 002_integrations.sql deliberately
# withholds the sealed columns from web_user, so asking for `*` there returns
# 403 by design and would fail this smoke on a correctly migrated database.
# Probing the primary key proves the table exists and is reachable, which is
# all this gate needs.
TABLES = [
    ("ah_snapshots", "*"), ("ah_configs", "*"), ("ah_logs", "*"),
    ("ah_client_configs", "*"),
    ("forecast_clients", "*"), ("proposals", "*"), ("proposal_votes", "*"),
    ("innovation_ideas", "*"), ("innovation_votos", "*"),
    ("innovation_comentarios", "*"), ("innovation_prototipos", "*"),
    # Integrations portal (M38) — 002_integrations.sql.
    ("integration_credentials", "id"),      # secret_sealed is write-only for web_user
    ("integration_connections", "id"),      # refresh_token_sealed idem
    ("integration_pending_grants", "id"),   # verifier_sealed / code_sealed idem
    ("integration_settings", "clave"),
    # Client accounts per authorization (Amazon Ads) — 006_integration_accounts.sql.
    ("integration_accounts", "id"),
    # Amazon Ads scheduled sync — 009_amazon_ads_sync.sql.
    ("integration_sync_jobs", "id"),
    ("ads_report_requests", "id"),
    ("ads_profile_sync", "profile_id"),
    ("ads_search_term_daily", "profile_id"),
    ("ads_portfolios", "profile_id"),
    ("integration_worker_heartbeats", "worker_name"),
    # Amazon Ads SB, SD and targets (M6, chat) — 015_targeting_sb_sd.sql.
    ("ads_sb_sd_campaign", "profile_id"),
    ("ads_sb_sd_campaign_daily", "profile_id"),
    ("ads_target", "profile_id"),
    ("ads_target_daily", "profile_id"),
    # Meli API bridge (M36) — 003_meli_api.sql + 004_meli_ads_unique.sql.
    ("meli_auth_identities", "id"),         # refresh_token_sealed idem
    ("meli_ingestion_runs", "id"),
    ("meli_item_snapshots", "id"),
    ("meli_rendimiento_diario", "id"),
    ("meli_ads_daily", "id"),
]
# Tables the app writes and never reads back: a refused read proves the grant, and that the table exists.
WRITE_ONLY_TABLES = [
    ("chat_turns", "id"),  # 016_chat_turns.sql
]
base = base.rstrip("/") + "/rest/v1/"
hdrs = {"Authorization": f"Bearer {key}", "apikey": key}
for table, columns in TABLES:
    req = urllib.request.Request(
        f"{base}{table}?select={columns}&limit=1", headers=hdrs
    )
    urllib.request.urlopen(req, timeout=10).read()  # raises on non-2xx (401 if the token is rejected)
    print("OK", table)
for table, columns in WRITE_ONLY_TABLES:
    req = urllib.request.Request(
        f"{base}{table}?select={columns}&limit=1", headers=hdrs
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403):
            raise
        print("OK", table, f"(write-only: read refused with {exc.code})")
        continue
    print(f"{table}: the app can read it, and it must only write it.")
    sys.exit(1)
print(f"DB smoke OK: {len(TABLES)} tables reachable, {len(WRITE_ONLY_TABLES)} write-only")

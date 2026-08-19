"""Read-only DB smoke: confirm the self-hosted PostgREST answers for every table.
Run inside the app container. No writes (safe on prod). Skips if the DB backend is off.
"""
import os
import sys
import urllib.request

base = os.environ.get("SUPABASE_URL")
if not base:
    print("DB backend not active (no SUPABASE_URL) — skipping DB smoke.")
    sys.exit(0)
key = os.environ.get("SUPABASE_KEY", "")  # the JWT PostgREST verifies; sent as the app does

TABLES = [
    "ah_snapshots", "ah_configs", "ah_logs", "ah_client_configs",
    "forecast_clients", "proposals", "proposal_votes",
    "innovation_ideas", "innovation_votos", "innovation_comentarios", "innovation_prototipos",
]
base = base.rstrip("/") + "/rest/v1/"
hdrs = {"Authorization": f"Bearer {key}", "apikey": key}
for t in TABLES:
    req = urllib.request.Request(base + t + "?limit=1", headers=hdrs)
    urllib.request.urlopen(req, timeout=10).read()  # raises on non-2xx (401 if the token is rejected)
    print("OK", t)
print(f"DB smoke OK: {len(TABLES)} tables reachable")

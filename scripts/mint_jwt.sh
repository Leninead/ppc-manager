#!/bin/sh
# Mint one of the portal's HS256 JWTs.
#
# The three tokens the stack needs are the same algorithm with a different
# `role` claim, all signed with PGRST_JWT_SECRET — that is what PostgREST
# verifies and what the column-level GRANTs key off:
#
#   web_user      SUPABASE_KEY  (the app) and INTEGRATIONS_RECEIVER_JWT
#   integ_worker  INTEGRATIONS_WORKER_JWT — the only role that reads sealed columns
#
#   sh scripts/mint_jwt.sh web_user      >> .env   # then name it
#   sh scripts/mint_jwt.sh integ_worker
#
# PGRST_JWT_SECRET is read from the environment, or from ./.env if unset.
set -eu
cd "$(dirname "$0")/.."

ROLE="${1:-integ_worker}"

if [ -z "${PGRST_JWT_SECRET:-}" ] && [ -f .env ]; then
  PGRST_JWT_SECRET="$(sed -n 's/^PGRST_JWT_SECRET=//p' .env | head -1)"
fi
if [ -z "${PGRST_JWT_SECRET:-}" ]; then
  echo "PGRST_JWT_SECRET is not set and .env does not define it." >&2
  exit 1
fi

PGRST_JWT_SECRET="$PGRST_JWT_SECRET" ROLE="$ROLE" python - <<'PY'
import base64, hashlib, hmac, json, os

def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

secret = os.environ["PGRST_JWT_SECRET"].encode()
# No `exp`: these are service tokens held by containers, and an expiry would
# silently stop the worker's cron in the middle of the night.
head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
body = b64(json.dumps({"role": os.environ["ROLE"]}, separators=(",", ":")).encode())
signed = f"{head}.{body}"
sig = b64(hmac.new(secret, signed.encode(), hashlib.sha256).digest())
print(f"{signed}.{sig}")
PY

#!/bin/sh
# Nightly backup of the self-hosted DB — layer 1 (local, dated, rotated).
# Off-site (Object Storage) is a TODO once a bucket exists. Wire via cron:
#   0 3 * * *  /srv/ppc-manager/deploy/db/backup.sh >> /srv/backups/backup.log 2>&1
set -eu
DB_CONTAINER="${DB_CONTAINER:-agency-db}"
DB="${DB:-agency_os}"
DIR="${BACKUP_DIR:-/srv/backups}"
KEEP="${KEEP:-14}"

mkdir -p "$DIR"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT="$DIR/agency_os_${STAMP}.dump"                   # pg_dump -Fc is already compressed
docker exec "$DB_CONTAINER" pg_dump -U postgres -Fc "$DB" > "$OUT"

# Integrations worker sealing keypair: not in the DB, lives in a docker volume.
# Losing it forces every connected seller to reauthorize their Meli account.
KEYS_VOL="${KEYS_VOL:-ppc-manager_integrations_keys}"
KEYS_OUT="$DIR/integrations_keys_${STAMP}.tgz"
if docker volume inspect "$KEYS_VOL" >/dev/null 2>&1; then
  docker run --rm -v "$KEYS_VOL":/src:ro -v "$DIR":/dst alpine \
    tar czf "/dst/$(basename "$KEYS_OUT")" -C /src .
fi

# Amazon Ads raw reports: Amazon keeps search terms 65 days, so these files are the only way to replay older days.
# Files are write-once, so an incremental mirror is enough; the mirror keeps them a bit longer than the worker's 180 days.
RAW_VOL="${RAW_VOL:-ppc-manager_ads_raw}"
RAW_KEEP_DAYS="${RAW_KEEP_DAYS:-190}"
if docker volume inspect "$RAW_VOL" >/dev/null 2>&1; then
  mkdir -p "$DIR/ads_raw"
  docker run --rm -v "$RAW_VOL":/src:ro -v "$DIR/ads_raw":/dst alpine \
    sh -c "cp -a -n /src/. /dst/ && find /dst -type f -mtime +$RAW_KEEP_DAYS -delete && find /dst -mindepth 1 -type d -empty -delete"
  echo "$(date -Is) ads raw mirror OK -> $DIR/ads_raw ($(du -sh "$DIR/ads_raw" | cut -f1))"
fi

# Rotation: keep the newest $KEEP of each kind.
ls -1t "$DIR"/agency_os_*.dump         2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
ls -1t "$DIR"/integrations_keys_*.tgz  2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

echo "$(date -Is) backup OK -> $OUT ($(du -h "$OUT" | cut -f1))"
[ -f "$KEYS_OUT" ] && echo "$(date -Is) keys backup OK -> $KEYS_OUT ($(du -h "$KEYS_OUT" | cut -f1))"

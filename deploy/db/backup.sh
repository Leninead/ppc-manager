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
OUT="$DIR/agency_os_$(date +%Y-%m-%d_%H%M%S).dump"   # pg_dump -Fc is already compressed
docker exec "$DB_CONTAINER" pg_dump -U postgres -Fc "$DB" > "$OUT"

# Rotation: keep the newest $KEEP, delete the rest.
ls -1t "$DIR"/agency_os_*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

echo "$(date -Is) backup OK -> $OUT ($(du -h "$OUT" | cut -f1))"

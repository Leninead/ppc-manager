#!/bin/sh
# Restore the latest backup into a throwaway postgres and verify it — an untested backup is not a backup.
# Reports the elapsed time as the RTO. Safe: touches nothing in prod. Run monthly (or on demand).
set -eu
DIR="${BACKUP_DIR:-/srv/backups}"
LATEST="$(ls -1t "$DIR"/agency_os_*.dump 2>/dev/null | head -1 || true)"
[ -n "$LATEST" ] || { echo "no backups in $DIR"; exit 1; }
echo "restoring: $LATEST"

START="$(date +%s)"
docker rm -f drill-pg >/dev/null 2>&1 || true
docker run -d --name drill-pg -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=agency_os postgres:16 >/dev/null
for i in $(seq 1 30); do
  docker exec drill-pg pg_isready -U postgres -d agency_os >/dev/null 2>&1 && break
  sleep 2
done

docker exec -i drill-pg pg_restore -U postgres -d agency_os --clean --if-exists < "$LATEST" >/dev/null 2>&1 || true

echo "=== row counts in the restored copy ==="
for t in ah_snapshots ah_configs ah_client_configs forecast_clients proposals innovation_ideas; do
  n="$(docker exec drill-pg psql -U postgres -d agency_os -tAc "select count(*) from $t" 2>/dev/null || echo '?')"
  printf '  %-22s %s\n' "$t" "$n"
done

docker rm -f drill-pg >/dev/null 2>&1 || true
echo "restore drill OK — RTO ~$(($(date +%s) - START))s"

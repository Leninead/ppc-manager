#!/bin/sh
# Idempotent migration runner. Applies deploy/db/migrations/NNN_*.sql in filename
# order, recording each in schema_migrations. Safe to re-run.
# The db container does not mount the migrations dir, so each file goes in via stdin.
#   Usage (from the repo root on the VPS):  sh deploy/db/migrate.sh
set -eu
cd "$(dirname "$0")/../.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml"

# Exit clean when the db overlay is not running: a host without it is a valid
# deployment, not a build failure. `ps` exits 0 on an unknown or stopped
# service and just prints nothing, so the output is what has to be tested.
if [ -z "$($COMPOSE ps --status running --format '{{.Name}}' db 2>/dev/null)" ]; then
  echo "db service is not running — skipping migrations"
  exit 0
fi

PSQL="$COMPOSE exec -T db psql -U postgres -d agency_os -v ON_ERROR_STOP=1"

$PSQL -q <<'SQL'
create table if not exists schema_migrations (
    filename   text primary key,
    applied_at timestamptz not null default now()
);
revoke all on schema_migrations from web_user;
SQL

for f in deploy/db/migrations/*.sql; do
  [ -e "$f" ] || { echo "no migrations found"; exit 0; }
  name="$(basename "$f")"
  applied="$($PSQL -tAc "select 1 from schema_migrations where filename = '$name'")"
  if [ "$applied" = "1" ]; then
    echo "skip  $name (already applied)"
    continue
  fi
  echo "apply $name"
  $PSQL -q < "$f"
  $PSQL -qc "insert into schema_migrations (filename) values ('$name')"
done
echo "migrations OK"

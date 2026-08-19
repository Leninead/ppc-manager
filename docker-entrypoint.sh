#!/bin/sh
# Seed the volume from the bundled skeleton (no-clobber: never overwrites client data), then exec.
set -eu
SEED_SRC="/app/seed"
DATA_DIR="${AGENCY_OS_DATA_DIR:-/app/data}"
if [ -d "$SEED_SRC" ]; then
  mkdir -p "$DATA_DIR"
  cp -rn "$SEED_SRC/." "$DATA_DIR/" 2>/dev/null || true
fi
exec "$@"

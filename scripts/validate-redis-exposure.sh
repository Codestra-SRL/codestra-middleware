#!/usr/bin/env bash
set -euo pipefail
compose=${COMPOSE_FILE:?set COMPOSE_FILE to the reviewed compose file}
if docker compose -f "$compose" config | grep -Eq '^[[:space:]]*ports:|0\.0\.0\.0:6379|:::6379'; then
  exit 1
fi
echo REDIS_PUBLIC_EXPOSURE_VALIDATION=PASS

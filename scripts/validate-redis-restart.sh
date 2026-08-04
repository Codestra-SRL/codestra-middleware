#!/usr/bin/env bash
set -euo pipefail
: "${REDIS_URL_FILE:?set REDIS_URL_FILE to an approved secret-mounted URL}"
test -s "$REDIS_URL_FILE"
echo REDIS_RESTART_VALIDATION=OPERATOR_CONTROLLED_REHEARSAL_REQUIRED

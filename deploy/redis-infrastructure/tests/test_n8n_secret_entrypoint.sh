#!/usr/bin/env bash
set -euo pipefail
script=$(dirname "$0")/../scripts/redis-secret-entrypoint.sh
grep -Fq "'exec /docker-entrypoint.sh \"\$@\"'" "$script"
grep -Fq 'HOME=/home/node' "$script"
grep -Fq 'N8N_USER_FOLDER=/home/node/.n8n' "$script"
if grep -Eq 'echo|printf|set -x|QUEUE_BULL_REDIS_PASSWORD=[^$]' "$script"; then
  exit 1
fi
echo N8N_ENTRYPOINT_ARGUMENT_SAFETY=PASS
echo N8N_RUNTIME_USER_CONTRACT=PASS
echo N8N_SECRET_OUTPUT=0

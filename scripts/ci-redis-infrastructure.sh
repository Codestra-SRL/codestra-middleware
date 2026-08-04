#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
for f in "$root"/scripts/*.sh; do bash -n "$f"; done
bash -n "$root/deploy/redis-infrastructure/scripts/redis-secret-entrypoint.sh"
bash "$root/deploy/redis-infrastructure/tests/test_n8n_secret_entrypoint.sh"
docker compose -f "$root/deploy/redis-infrastructure/compose.profiles.example.yaml" config >/dev/null
python3 -m json.tool "$root/monitoring/grafana/redis-overview.dashboard.json" >/dev/null
python3 "$root/tests/test_redis_infrastructure.py"
if grep -RInE 'redis_password[[:space:]]*:[[:space:]]*[^<{[:space:]]|QUEUE_BULL_REDIS_PASSWORD[[:space:]]*:[[:space:]]*[^<{[:space:]]|BEGIN (RSA|OPENSSH) PRIVATE KEY' "$root/deploy/redis-infrastructure" "$root/monitoring" --exclude='*.md' --exclude='*.json' --exclude='*.sh'; then
  exit 1
fi
echo REDIS_INFRASTRUCTURE_CI=PASS

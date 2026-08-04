#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
for f in "$root"/scripts/*.sh; do bash -n "$f"; done
python3 -m json.tool "$root/monitoring/grafana/redis-overview.dashboard.json" >/dev/null
python3 "$root/tests/test_redis_infrastructure.py"
! grep -RInE 'redis_password|QUEUE_BULL_REDIS_PASSWORD=|password[[:space:]]*:[[:space:]]*[^<{[:space:]]' "$root" --exclude='*.md' --exclude='*.json'
echo REDIS_INFRASTRUCTURE_CI=PASS

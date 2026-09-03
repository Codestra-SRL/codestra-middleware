#!/usr/bin/env bash
set -euo pipefail
conf=${REDIS_CONFIG_PATH:-/etc/redis/redis.conf}
test -r "$conf"
grep -Eq '^(appendonly[[:space:]]+)yes' "$conf"
grep -Eq '^(maxmemory-policy[[:space:]]+)noeviction' "$conf"
echo REDIS_CONFIGURATION_VALIDATION=PASS

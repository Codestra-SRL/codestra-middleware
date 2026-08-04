#!/usr/bin/env bash
set -euo pipefail
acl=${REDIS_ACL_PATH:-/run/secrets/redis-users.acl}
test -r "$acl"
grep -Eq '^user default off' "$acl"
grep -Eq '^user middleware-service on' "$acl"
grep -Eq '^user n8n-service on' "$acl"
grep -Eq -- '-flushall|-@admin' "$acl"
! grep -Eq 'redis_password|QUEUE_BULL_REDIS_PASSWORD|BEGIN (RSA|OPENSSH) PRIVATE KEY' "$acl"
echo REDIS_ACL_POLICY_VALIDATION=PASS

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
acl = (ROOT / 'deploy/redis-infrastructure/redis.acl.template').read_text()
compose = (ROOT / 'deploy/redis-infrastructure/compose.redis-security.example.yaml').read_text()
rules = (ROOT / 'monitoring/prometheus.redis.rules.yml').read_text()
assert 'user default off' in acl
assert 'user middleware-service on' in acl
assert 'user n8n-service on' in acl
assert '-flushall' in acl and '-@admin' in acl
assert 'ports:' not in compose
assert 'redis_middleware_password' in compose and 'redis_n8n_password' in compose
assert 'redis_password' not in (acl + compose)
for alert in ('CodestraRedisDown', 'CodestraRedisHighMemory', 'CodestraRedisEvictions', 'CodestraRedisPersistenceFailure', 'CodestraRedisAuthenticationFailures', 'CodestraRedisUnexpectedAclDenials', 'CodestraN8nQueueBacklog'):
    assert alert in rules
json.loads((ROOT / 'monitoring/grafana/redis-overview.dashboard.json').read_text())
print('REDIS_INFRASTRUCTURE_STATIC_TEST=PASS')

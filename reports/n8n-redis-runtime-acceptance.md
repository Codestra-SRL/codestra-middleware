# n8n and Redis runtime staging acceptance

Captured on Middleware Server A (`65.109.65.169`) using synthetic-only data.
Production writes, Odoo mutations, VICIdial database access, outreach, and paid
AI/provider calls remained disabled.

## Runtime inventory

```text
MIDDLEWARE_BASE_SHA=289047c9a2a2e0585df2faca37270ae4c0a4a9bc
REDIS_VERSION=7.4.5
REDIS_HOST=codestra-n8n-staging-redis-1
REDIS_PRIVATE_IP=172.24.0.3
REDIS_PERSISTENCE_MODE=AOF=yes; snapshot=60/1
REDIS_MEMORY_LIMIT=256 MiB container; 192 MiB Redis; noeviction
N8N_VERSION=2.30.8
N8N_HOST=n8n-staging.codestra.agency
N8N_PRIVATE_IP=10.254.40.2
N8N_DATABASE=PostgreSQL (n8n_staging)
N8N_EXECUTION_MODE=queue
N8N_WORKER_COUNT=2
N8N_CONCURRENCY=10 total (5 per worker)
WORKFLOWS_TOTAL=237
WORKFLOWS_ACTIVE_APPROVED=1 (TEST_SYN Codestra Governed Runtime V1)
WORKFLOWS_INACTIVE_APPROVED=0
WORKFLOWS_OBSOLETE=0
WORKFLOWS_DUPLICATE=0
WORKFLOWS_UNKNOWN=236
WORKFLOWS_UNSAFE=0 confirmed; governance classification remains unknown
```

Redis publishes no host port and public TCP/6379 connection failed. The
`n8n-service` ACL authenticates queue operations and is denied CONFIG/ACL
administration. TLS is not enabled on this container-local private network.

## Canary and recovery

```text
CONCURRENT_DUPLICATE_10=PASS (one 202, nine 200, one durable execution)
SIGNED_RESULT=PASS (202)
RESULT_REPLAY=PASS (409 rejected)
RESULT_DUPLICATE=PASS (200; one durable result)
MIDDLEWARE_RESTART=PASS (pending execution recovered and dispatched)
REAL_N8N_DISPATCH_CALLBACK=PASS (one execution; one durable result)
N8N_REPLAY_PROTECTION=PASS (identical signed callback returned 409)
CONCURRENT_DUPLICATE_10=PASS (one logical n8n execution/result)
MIDDLEWARE_RESTART=PASS (bounded callback retry; no lost result)
N8N_RESTART=PASS (queued execution recovered; one result)
REDIS_RESTART=PASS (healthy PONG; durable n8n count unchanged)
REAL_N8N_RESTART=PASS (main, webhook, and two workers healthy)
ODOO_WRITE_COUNT=0
VICIDIAL_WRITE_COUNT=0
OUTREACH_EVENT_COUNT=0
```

The canary identified and remediated stale dispatch-lease recovery and detached
ORM transition persistence before certification.

## Performance

At real n8n concurrency 25 there were 25 successful creations and executions,
zero duplicates, zero failures, and zero timeouts:

```text
MIDDLEWARE_TO_N8N_P50_MS=839.823
MIDDLEWARE_TO_N8N_P95_MS=867.651
MIDDLEWARE_TO_N8N_P99_MS=873.964
N8N_EXECUTION_P50_MS=40.000
N8N_EXECUTION_P95_MS=175.400
N8N_EXECUTION_P99_MS=452.640
RESULT_CALLBACK_P50_MS=16.773
RESULT_CALLBACK_P95_MS=91.405
RESULT_CALLBACK_P99_MS=100.053
ROUND_TRIP_P50_MS=2396.575
ROUND_TRIP_P95_MS=3647.613
ROUND_TRIP_P99_MS=3678.856
REDIS_PING_P50_MS=0.031
REDIS_PING_P95_MS=0.039
REDIS_PING_P99_MS=0.047
SAFE_STAGING_CONCURRENCY=25
```

The synthetic workflow uses n8n's encrypted Crypto credential store; the HMAC
secret is projected separately to middleware from a root-owned server file.
The Odoo-bound canary remains outside this branch's certified evidence because
the governed n8n result is intentionally retained in middleware PostgreSQL and
no approved synthetic result-to-Odoo mapping was activated.

## Validation

```text
TESTS=873 passed; 20 skipped
FOCUSED_RUNTIME_TESTS=26 passed
RUFF=PASS
MYPY=PASS (151 source files)
BANDIT=PASS (zero findings after remediation)
PIP_AUDIT=PASS (no known vulnerabilities)
TRIVY=PASS (candidate image: zero HIGH/CRITICAL vulnerabilities or secrets)
GITLEAKS=PASS
MIGRATION=PASS (0033 -> 0034 -> 0033 -> 0034)
OPENAPI=PASS (178 paths; 81 schemas)
```

## Findings and external gates

- Medium: all 236 staging workflows are inactive and lack a signed governance
  inventory classification; none was deleted or activated.
- External gate: a governance-approved synthetic result-to-Odoo mapping is
  required before the Odoo-bound canary can run without enabling arbitrary
  n8n-to-Odoo writes.

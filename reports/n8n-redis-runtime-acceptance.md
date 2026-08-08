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
REDIS_MEMORY_LIMIT=not configured (Docker and Redis command)
N8N_VERSION=2.30.8
N8N_HOST=n8n-staging.codestra.agency
N8N_PRIVATE_IP=10.254.40.2
N8N_DATABASE=PostgreSQL (n8n_staging)
N8N_EXECUTION_MODE=queue
N8N_WORKER_COUNT=2
N8N_CONCURRENCY=10 total (5 per worker)
WORKFLOWS_TOTAL=236
WORKFLOWS_ACTIVE_APPROVED=0
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
SYNTHETIC_N8N_RESTART=PASS (network failure -> RETRY -> dispatched)
REDIS_RESTART=PASS (healthy PONG; durable n8n count unchanged)
REAL_N8N_RESTART=PASS (main, webhook, and two workers healthy)
ODOO_WRITE_COUNT=0
VICIDIAL_WRITE_COUNT=0
OUTREACH_EVENT_COUNT=0
```

The canary identified and remediated stale dispatch-lease recovery and detached
ORM transition persistence before certification.

## Performance

At synthetic concurrency 1/5/10/25 there were 41 successful creations, 41
successful transport dispatches, zero duplicates, zero failures, and zero
timeouts. At concurrency 25:

```text
MIDDLEWARE_ACCEPT_P50_MS=242.028
MIDDLEWARE_ACCEPT_P95_MS=261.378
MIDDLEWARE_ACCEPT_P99_MS=261.958
MIDDLEWARE_TO_N8N_P50_MS=3.952
MIDDLEWARE_TO_N8N_P95_MS=4.971
MIDDLEWARE_TO_N8N_P99_MS=5.351
RESULT_CALLBACK_SAMPLE_MS=56.136
REDIS_PING_P50_MS=0.031
REDIS_PING_P95_MS=0.039
REDIS_PING_P99_MS=0.047
SAFE_STAGING_CONCURRENCY=25
```

Actual n8n workflow execution latency and the Odoo-bound canary are not
certified because all staging workflows are inactive and no approved
`TEST_SYN_*` workflow/HMAC credential mapping is available. Nothing was
activated or modified directly in the n8n database.

## Validation

```text
TESTS=963 passed; 20 skipped
FOCUSED_RUNTIME_TESTS=24 passed
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

- Medium: staging Redis has no configured maxmemory/eviction ceiling. Changing
  the independent n8n infrastructure compose requires its owning repository and
  review.
- Medium: all 236 staging workflows are inactive and lack a signed governance
  inventory classification; none was deleted or activated.
- External gate: an approved inactive `TEST_SYN_*` workflow plus the n8n-side
  HMAC credential mapping is required for real workflow execution and the
  Odoo-bound staging canary.

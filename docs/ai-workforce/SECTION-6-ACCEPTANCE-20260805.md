# Section 6 staging acceptance — 2026-08-05

## Runtime evidence

- n8n staging image is pinned and reports version `2.30.8`.
- n8n main, webhook, and two worker containers were healthy/running. Main and
  workers report `EXECUTIONS_MODE=queue`; workers report concurrency `5`.
- n8n public API is disabled, node environment access is blocked, community and
  unverified packages are disabled, external delivery/write flags are false.
- 236 workflows are present in the staging database and 0 are active.
- Redis staging reports Redis `7.4.5`, AOF enabled, `noeviction`, and no
  configured maxmemory. The n8n service ACL is limited to `n8n:*` and `bull:*`
  key patterns and cannot run `SCAN`, `CONFIG`, or `ACL`; recovery access is a
  separate operator identity.
- Synthetic Redis idempotency reservation, lock contention, queue push/pop,
  TTL, and cross-prefix denial checks passed.
- Redis restart preserved a synthetic AOF-backed key. n8n workers reconnected;
  worker restart returned to ready state with concurrency 5.
- n8n workflow/database backup completed at
  `/opt/codestra/n8n-staging/backups/20260805T132133Z/`; SHA-256 verification
  passed. Disposable PostgreSQL restore produced 236 workflow records.
- Redis PING p95 was 0.071 ms (200 samples). n8n `/healthz` p95 was 0.949 ms
  (50 samples). No active workflow was available for a customer-visible callback
  latency run because all staging workflows remain inactive by policy.

## Test evidence

- Full regression in disposable Python 3.12.13 runtime: **872 passed, 7
  skipped**.
- Section 6 orchestration-focused tests: **16 passed**.
- Ruff checks: **pass**.
- Runtime callback/external-write tests were not fabricated: no active workflow
  or approved signed callback fixture was enabled, and no external provider
  action was performed.

## Acceptance decision

The implementation and staging infrastructure checks pass. Formal production
activation remains disabled. Callback throughput, incomplete-execution replay,
and external-write deduplication require an approved synthetic workflow fixture
and signed callback credentials before they can be marked runtime PASS.

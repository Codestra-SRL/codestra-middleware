# Qwen worker bounded concurrency

The outbound-only Qwen worker runs one poller and a bounded two-slot thread executor. A slot owns one claimed job from claim through heartbeat, inference, cancellation, and fenced completion. Jobs do not share cancellation events, fencing tokens, inference processes, or result state.

## Effective limit

The worker calculates its limit as:

```text
min(QWEN_MAX_IN_PROCESS_JOBS, registration.max_concurrency, 2)
```

The authenticated `/internal/api/v1/ai/worker/config` response supplies the registration limit. Missing or invalid registration configuration fails closed. The hard safety cap is two. The deployed unit defaults to `QWEN_MAX_IN_PROCESS_JOBS=1`, preserving the certified behavior until a separately governed canary changes both the local setting and registration.

The poller requests a lease only after confirming that a local slot is free. There is no leased-but-waiting local queue. Reducing registration capacity stops new claims but does not corrupt an already fenced job lifecycle.

## Shutdown and recovery

SIGTERM and SIGINT stop polling immediately and signal every active slot. Each slot terminates its inference subprocess and releases its fenced lease through the authenticated release endpoint. A failed release is treated as lease loss; no result is committed afterward. Controller recovery remains tenant and workspace scoped.

## Metrics

The worker emits a bounded-cardinality JSON metric snapshot every 30 seconds and at shutdown. Metric names are:

- `codestra_ai_worker_active_jobs`
- `codestra_ai_worker_available_slots`
- `codestra_ai_worker_configured_concurrency`
- `codestra_ai_worker_effective_concurrency`
- `codestra_ai_worker_claims_total`
- `codestra_ai_worker_over_capacity_claim_attempts`
- `codestra_ai_worker_job_latency_seconds`
- `codestra_ai_worker_heartbeat_failures_total`
- `codestra_ai_worker_cancellations_total`

No job, tenant, workspace, or credential identifier is used as a metric label.

## Rollback

Set the registration `max_concurrency` and `QWEN_MAX_IN_PROCESS_JOBS` back to `1`, then restart only the worker service. Verify one worker process, effective concurrency one, queue health, and maximum observed overlap one. The currently certified production canary must remain at one until the immutable concurrency-two candidate passes its dedicated canary.

# Worker safety contract

The worker must validate scope and canonical hashes, durably reserve one
attempt, fsync forensic intent, verify a short-lived activation-bound runtime
attestation for the exact Compose service/container/image/internal network,
verify health and readiness, submit once, capture and fsync the bounded
response, validate the schema-selected acknowledgement, then finalize.

The state progression is `RESERVED_DURABLE`, `HTTP_ATTEMPTED`,
`RESPONSE_CAPTURED`, `EVIDENCE_FSYNCED`, `ACK_VALIDATED`, `COMPLETED`.
Crashes terminalize without resend. Transport failures receive a durable
zero-response diagnostic. Evidence failure is terminal. Public, loopback,
legacy, ambiguous, stale, unsigned, or mismatched targets are rejected.

The high-water mark, lifecycle allowlist, exact scope, 25-request cap,
one-attempt rule, no-retry rule, stop-on-first-failure circuit breaker, and
automatic restoration to `SEND_EVENTS=false` are mandatory.

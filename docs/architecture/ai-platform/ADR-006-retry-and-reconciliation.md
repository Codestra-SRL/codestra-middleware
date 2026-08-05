# ADR-006: Retry and reconciliation

## Context
Distributed calls can fail after transmission, producing ambiguous outcomes.

## Decision
Temporary failures retry with bounded backoff; ambiguous outcomes enter `UNKNOWN` and are resolved by reconciliation. Permanent and security failures do not retry automatically.

## Alternatives considered
Unbounded retries and exactly-once delivery were rejected.

## Security and reliability
Idempotency keys and result deduplication prevent duplicate effects.

## Operations and rollback
Reconciliation defaults to dry-run and can be paused independently.

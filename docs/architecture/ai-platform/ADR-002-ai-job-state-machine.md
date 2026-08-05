# ADR-002: AI job state machine

## Context
AI work is asynchronous and can time out or need approval.

## Decision
Jobs use explicit states from `RECEIVED` through `RUNNING`, `RESULT_VALIDATION`, `COMPLETED`, `FAILED`, `UNKNOWN`, and cancellation/retry states. Invalid transitions are rejected.

## Alternatives considered
An untyped status flag was rejected because it cannot support reconciliation or safe retries.

## Security and reliability
Every transition is audited and terminal jobs cannot be overwritten by a callback.

## Operations and rollback
Retry creates an audited new attempt; rollback pauses dispatch without deleting history.

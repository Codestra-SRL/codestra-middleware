# VICIdial idempotency

Assignment items have a unique external key and batch idempotency key. Retries search by external key before create. Timeouts become `ASSIGNMENT_UNKNOWN` and require reconciliation; they never blindly create a second lead.

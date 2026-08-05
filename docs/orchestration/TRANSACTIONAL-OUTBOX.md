# Transactional outbox

Command and outbox publication intent commit together. Dispatch is at-least-once,
lease-based, retryable, and idempotent; PostgreSQL survives Redis loss.

# Events

Events are immutable, schema-versioned, idempotent, replayable records. Event
ingestion is disabled by default; consumers must use durable outbox/inbox and
reconciliation semantics.

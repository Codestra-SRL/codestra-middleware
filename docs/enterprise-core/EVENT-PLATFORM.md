# Enterprise event platform baseline

## Operational delivery

PostgreSQL is authoritative for subscriptions, deliveries, retries, replays,
and dead letters. Publication idempotently materializes deliveries. Workers use
`FOR UPDATE SKIP LOCKED`, bounded leases, exponential backoff, and a hard retry
ceiling; expired leases survive process and application restart. Replay requeues
the durable delivery without creating a second external-action record.

Subscriptions are tenant/workspace scoped, created disabled pending review,
and use allowlisted endpoint keys rather than arbitrary URLs. Dead-letter retry
is restricted to the caller's validated scope.

The existing PostgreSQL inbox/outbox is the delivery foundation. Events are
immutable, schema-versioned, tenant/workspace scoped, idempotent, correlated,
and auditable. Redis or NATS may notify workers but cannot be the source of
truth.

At-least-once delivery is the default. Exactly-once effects are obtained only
through atomic inbox uniqueness and downstream idempotency keys. Failed events
use bounded retries, exponential backoff, circuit breaking, dead-letter state,
and explicitly authorized replay. Replay never changes the original event.

Section 5 must extend the existing tables rather than create a competing event
store and must prove ordering, duplicates, restart recovery, overflow behavior,
tenant isolation, and replay authorization against PostgreSQL.

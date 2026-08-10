# Phase N8 n8n path

The synthetic event is committed to PostgreSQL before n8n work begins. A unique `(event_id, target)` delivery is leased and mapped once to a governed `N8nRuntimeExecution`. The test completes that execution through the established result boundary and verifies that reconciliation marks the delivery delivered.

An expired lease is changed to `retry_wait`, proving worker-crash recovery without losing the canonical event. Existing n8n authentication, replay, callback, outage, and idempotency suites remain part of the repository-wide gate.

The N7 identity, lead-intelligence, next-action, and attribution workflows remain inactive source-controlled artifacts. Phase N8 does not promote them to shared production n8n and does not claim a real external workflow execution ID.

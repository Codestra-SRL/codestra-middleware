# Event catalog

Events are stored before delivery and retain the original payload plus a normalized representation. Event IDs and idempotency keys are unique. Duplicate receipts return the original acknowledgement and cannot repeat business effects.

Normalized families include lead, call, agent, callback, integration delivery, dead-letter, adapter-health, and n8n-health events. Every event carries schema version, producer, environment, correlation ID, and causation ID.

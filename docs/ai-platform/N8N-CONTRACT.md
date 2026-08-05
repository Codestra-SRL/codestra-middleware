# n8n contract

The outbox delivers versioned events with message, event, correlation, causation, tenant, and workflow routing identifiers. n8n returns a signed result containing job, workflow, execution, schema, status, and payload metadata. Unknown workflows, schemas, tenants, replays, and malformed payloads are rejected.

# Codestra AI Platform control plane

This foundation adds durable AI jobs, approvals, lead-search records, registries, signed workflow-result ingestion, and reconciliation metadata to the existing middleware. Provider execution, scraping, and application writes are intentionally out of scope.

All requests enter middleware, are persisted before outbox delivery, and are scoped by tenant. n8n is an orchestrator; it cannot become the system of record.

## Safe defaults

AI inference, external providers, discovery, imports, Odoo/VICIdial/Postly writes, workflow activation, transcription, and call analysis are disabled by default.

## Endpoints

AI jobs: `/api/v1/ai/jobs`; approvals: `/api/v1/ai/approvals`; lead intelligence: `/api/v1/lead-intelligence`. Signed n8n callbacks use `/api/v1/ai/jobs/{job_id}/result` and the existing HMAC service identity.

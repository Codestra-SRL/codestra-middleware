# n8n AI routing

`CDA-AI-00` must select workflows from a server-controlled route map. Payloads cannot select arbitrary workflow names. Every export is inactive and references credential names only. Result callbacks target the middleware contract and must include job, execution, tenant, correlation, schema, and idempotency identifiers.

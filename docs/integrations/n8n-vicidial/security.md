# Security controls

- Middleware authenticates service calls and enforces action, tenant, campaign, consent, suppression, calling-hours, and feature-flag policy.
- n8n callbacks use body hashes, timestamps, nonces, signatures, schema and environment checks. Replayed nonces and modified payloads are rejected.
- Provider credentials are root-owned mode-600 files or Docker secrets and never appear in workflow JSON, source, logs, or evidence.
- Redis ACLs isolate `codestra:*` middleware namespaces from `n8n:*` and `bull:*`.
- PostgreSQL and Redis have no public host exposure in the staging runtime.
- Security failures are non-retryable and cannot fail open.

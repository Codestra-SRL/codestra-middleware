# Monitoring

Prometheus and Alertmanager cover command/event volume, outbox lag, n8n execution failures, provider adapter failures, dead-letter growth, callback backlog, reconciliation mismatch, and stale execution conditions. Labels are low-cardinality and exclude customer IDs, phone numbers, email addresses, credentials, traces, and raw error messages.

Runtime notification delivery requires monitoring endpoints and owner access on the target deployment.

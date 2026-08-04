# API contract inventory

The implementation exposes compatible durable contract families:

- `/api/v1/commands` and `/api/v1/telephony/operations` for command intake, transitions, results, cancellation, and reconciliation.
- `/api/v1/events/vicidial` for authenticated, nonce-protected event ingestion.
- `/api/v1/n8n/executions` and `/api/v1/n8n/acknowledgements` for durable n8n registration and result acknowledgement.
- `/api/v1/integrations/n8n/*` for approved-order callbacks.
- `/api/v1/integrations/vicidial/commands*` and `/api/v1/integrations/postiz/commands*` for provider command contracts.

Mutating requests are versioned, validated, authenticated, and idempotent. Administrative replay and cancellation require elevated authorization.

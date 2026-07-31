# Lead Automation HMAC-V2 Contract

The n8n result callback uses `HMAC-V2` and the exact scope
`lead-automation.results.write`. Its canonical material is defined by
`app/core/lead_callback_auth.py` and binds, in order, signature version,
uppercase method, canonical path, timestamp, nonce, service identity, service
audience, environment, exact scope, idempotency key, and exact-body SHA-256.

The only HMAC-V2 lead-automation callback currently exposed by Middleware is
`POST /api/v1/lead-automation/results`. Registration and terminal
acknowledgement endpoints use their existing JWT-authenticated n8n transport
contract and are not HMAC callers. A result signature cannot authorize those
capabilities because the result scope and path are exact and neither endpoint
accepts this HMAC credential.

Missing or unsupported versions; empty, wildcard, or cross-capability scopes;
unexpected queries; ambiguous paths; expired timestamps; nonce replay; body
changes; and identity, audience, environment, method, or path changes are
rejected before result processing. HMAC-V1 fallback is not implemented.

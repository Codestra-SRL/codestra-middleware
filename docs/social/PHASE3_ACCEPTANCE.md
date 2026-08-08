# Phase 3 acceptance

Implemented and locally testable: durable hash-only OAuth state with atomic single-use consumption, OAuth exchange/refresh, mode-0600 token storage, profile normalization, message scheduling/cancellation/status lookup, media initialization, normalized errors/rate limits, unknown-result fail-closed behavior, deterministic new-operation canary routing, historical ownership, and rollback rules.

Real Postly read authentication, health, and empty account discovery are certified on
the private route. Postly writes remain blocked because there are no staging-safe
accounts. The Hootsuite developer app and credentials are absent, so real Hootsuite
OAuth, token refresh, health, account discovery, media transfer, schedule/cancel,
polling reconciliation, and the provider canary remain externally blocked. Phase 3
must remain partial and disabled. See `PHASE3A_PROVIDER_AUTH.md`.

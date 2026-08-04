# Command catalog

Commands are persisted before dispatch and carry command ID, idempotency key, correlation/causation IDs, schema version, expiry, actor, subject, and environment. Middleware enforces the allowlist; n8n cannot select a free-form provider operation.

The VICIdial contract supports agent, extension, campaign, list, lead, callback, manual/preview test-call, result, recording metadata, agent-state, and reconciliation commands. Predictive dialing, bulk lead import, direct SQL, customer messaging, and unrestricted provider operations are rejected.

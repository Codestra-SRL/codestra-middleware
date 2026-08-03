# Integration rollback

No production integration configuration was activated in this phase. Rollback therefore means remove/disable only a future adapter overlay and secret reference, restore the pinned Compose/Caddy configuration, and verify the existing v2.22.1 image digest and all eight health checks.

Before any activation, create a fresh encrypted snapshot and record it in the change ticket. Stop order: adapter traffic, Postiz application, workers; preserve data services. Start order: PostgreSQL/Redis/Temporal/Elasticsearch, verify readiness, then Postiz and proxy probe. Database restoration requires explicit rollback authority and the verified logical dump. Canonical production rollback runbook: `/srv/postiz/documentation/rollback.md`.

Triggers: failed health check, database migration error, organization-isolation failure, credential leakage, duplicate schedule evidence, OAuth callback breakage, or sustained 5xx. Social publication cannot be undone reliably; this is why canary writes require separate authorization.

# Phase 2 controlled staging

Phase 2 extends the provider-neutral foundation with a PostgreSQL repository, persistent idempotency, job leases, Redis signaling, a single-concurrency worker, persistent webhook receipts, and IntegrationEvent creation. Source defaults remain off and no production service is deployed.

Middleware Server A is `65.109.65.169`. The intended Postly server is `49.12.145.107`, with expected VLAN peers `10.40.0.1` and `10.40.0.2`. At discovery time the Postly peer and SSH identity were unavailable, so real API/auth/account/webhook tests remain externally blocked. Local disposable PostgreSQL tests validate durable behavior without provider side effects.

Before staging activation, provision approved access, confirm a `STAGING_SAFE` account, install secrets as files, enable only isolated staging overrides, and rerun the acceptance matrix. `SOCIAL_PUBLISH_ENABLED` and all Odoo write flags remain false.

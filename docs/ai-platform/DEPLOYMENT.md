# Deployment

Run the existing Alembic migration workflow and verify revision `0033` in an isolated staging database. Do not apply it to production without a reviewed backup and rollback plan. No provider credentials are required for the control-plane foundation.

The application, database, outbox, and result inbox must be healthy before enabling any staging test. Keep all application-write switches false.

# Healthcare transportation architecture

Server A (`65.109.65.169`) owns tenant-scoped patients, facilities, trips, dispatch, billing, audit, and reconciliation. Server B (`5.9.108.250`) provides private, middleware-controlled administrative AI. Server C (`49.12.145.107`) provides only approved routing and health checks. Server D (`65.21.67.207`) provides narrowly scoped call-center integration.

Browsers and mobile clients use middleware APIs only. Production deployment, real providers, notifications, automatic dispatch, and clinical decisions are disabled in this foundation.

# Authenticated scraper ingress overlay

This overlay configures only the existing hardened Middleware integration API.
It does not enable ingress by default and does not create credentials. Render it
with the protected runtime Compose file only after Security enrolls the exact
Keycloak service client and installs one to three service-owned HMAC key files.

Each key filename is `<key-id>.key`; the directory must be owned by runtime UID
`10001` with mode `0700`, and each file must be a regular, non-symlink `0600`
file owned by that UID and containing at least 32 bytes. Set
`SALES_SCRAPER_HMAC_KEY_IDS` to the exact comma-separated filename stems. An
overlap permits rotation; unknown keys and HMAC-v1 fail closed.

Before setting `SCRAPER_RESULT_INGEST_ENABLED=true`, verify that the JWT client
has audience `codestra-scraper-ingress`, scope `scraper.events.write`, realm
role `scraper-publisher`, and exact environment, tenant, and campaign claims.
The configured authorized party must equal `SALES_SCRAPER_IDENTITY`.

Rollback begins by setting `SCRAPER_RESULT_INGEST_ENABLED=false` and recreating
only `middleware-integration-api`. Preserve the PostgreSQL inbox and audit rows;
do not delete or replay accepted events. Removing an old HMAC key is allowed
only after its bounded overlap window and accepted-request reconciliation.

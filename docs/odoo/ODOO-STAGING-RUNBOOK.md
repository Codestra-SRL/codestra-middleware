# Staging runbook

Use only `TEST_SYN_` records and the dedicated staging tenant. Confirm the reviewed addon mount, healthy Odoo registry, private network DNS, CA validation, and short-lived client-credentials JWT before enabling reads. Run authenticated live/readiness/capabilities probes, then read canaries. Next create one synthetic Odoo outbox event and prove claim/lease/durable middleware intake/ACK with result delivery disabled.

Only after that gate may operators enable `ODOO_RESULT_DELIVERY_ENABLED` and `ODOO_STAGING_WRITES_ENABLED`. `ODOO_PRODUCTION_WRITES_ENABLED` and `LIVE_WRITES_ENABLED` stay false. Validate one allowlisted synthetic result and compare exact before/after records. Disable staging writes immediately after certification.

Current blocker: no valid staging service JWT/client secret is available to the middleware worker. The existing opaque test token is not a JWT and is correctly rejected. Do not bypass authentication.

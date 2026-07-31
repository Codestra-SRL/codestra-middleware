# Inactive n8n staging import

Import `/source/lead-automation/lead-automation-generic-v1.json` only into the
isolated staging n8n container. Do not use a live credential ID. Bind the
runtime secret after import and leave `n8n.leads.ingest` disabled.

Immediately export or query the imported workflow and fail unless `active` is
strictly `false`. Fail if the binding candidate is enabled, if an execution was
created, or if a node falls outside `node-allowlist-v1.json`. The source permits
only the Middleware callback target; direct Odoo, database, communication, and
recording access are prohibited.

Rollback deletes the staging-only imported workflow and credential binding,
then verifies zero executions. This preparation phase performs no import.

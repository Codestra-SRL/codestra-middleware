# Odoo staging installation, upgrade, and rollback

The only permitted database is `codestra_odoo_lead_staging` on service
`odoo-postgres`. Preflight must reject all other hosts and database names.

With all switches false, run a one-shot Odoo 19 container using the pinned
image and exact addons checkout. Install `codestra_lead_automation` with
`--init`, then test upgrade with `--update`, both using `--stop-after-init`.
Validate HMAC-V2 rejection/acceptance, ACLs, multi-company isolation, consent,
DNC, idempotency, and acknowledgement classification. The running service may
start only after these checks pass.

Rollback stops Odoo, restores the encrypted staging-only database and filestore
backup, verifies checksums, and keeps the apply flag false. Uninstall safety is
tested only in a disposable clone of the staging database.

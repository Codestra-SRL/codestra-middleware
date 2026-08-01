# Odoo staging installation, upgrade, and rollback

The only permitted database is `codestra_odoo_lead_staging` on service
`odoo-postgres`. Preflight must reject all other hosts and database names.

With all switches false, run a one-shot Odoo 19 container using the pinned
image and exact addons checkout. Install `codestra_lead_automation` with
`--init`, then test upgrade with `--update`, both using `--stop-after-init`.
Validate HMAC-V2 rejection/acceptance, ACLs, multi-company isolation, consent,
DNC, idempotency, and acknowledgement classification. The running service may
start only after these checks pass.

The executable multi-company test is
`codestra_lead_automation/tests/test_multicompany_isolation.py` at Odoo PR #15
head `d6d2c6aff858f154eabad38b04203c507552f38e`. Run it only against an ephemeral
PostgreSQL database with the digest-pinned Odoo 19 image:

```sh
odoo --database=lead_automation_mc_ci \
  --init=codestra_lead_automation --without-demo=True --test-enable \
  --test-tags=/codestra_lead_automation:LeadAutomationMultiCompanyIsolationTest \
  --stop-after-init
```

The fixtures create only `synthetic-logistics-a` and
`synthetic-logistics-b`. Evidence must show same-company access succeeds while
cross-company lead, campaign, business-unit, and numeric-record substitution
are denied without CRM or callback mutation. Remove the disposable database,
container, and internal network after the test. Production databases and data
are prohibited.

Rollback stops Odoo, restores the encrypted staging-only database and filestore
backup, verifies checksums, and keeps the apply flag false. Uninstall safety is
tested only in a disposable clone of the staging database.

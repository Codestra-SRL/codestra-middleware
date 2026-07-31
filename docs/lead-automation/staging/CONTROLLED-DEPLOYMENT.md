# Controlled isolated staging deployment

Each step requires recorded preconditions, evidence, failure disposition, and
rollback before continuing:

1. Recheck exact source heads, CI, and preparation approval; stop on drift.
2. Verify Server A identity and capacity; stop on collision or pressure.
3. Create the unique internal network and volumes; remove them on failure.
4. Generate staging-only secrets and record fingerprints; revoke on failure.
5. Start only staging PostgreSQL and Redis; verify no external attachment.
6. Back up the empty databases and verify encrypted checksums.
7. Run the one-shot Middleware migration; require the sole 0029 merge head.
8. Start Middleware with every switch false; stop it on readiness failure.
9. Install/upgrade the Odoo module in the staging database; restore on failure.
10. Start isolated n8n, import inactive, and assert zero executions.
11. Register the candidate binding disabled; delete it on assertion failure.
12. Run no-mutation and synthetic default-off acceptance tests.
13. Verify observability, reconciliation, and kill-switch alerts.
14. Produce deployment evidence. Enable no feature flag and stop before any
    activation phase.


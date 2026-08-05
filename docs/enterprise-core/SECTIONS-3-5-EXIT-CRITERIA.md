# Sections 3–5 exit-criteria program

Section 6 remains unauthorized. This program does not add columns or modify a
shared database. It converts the current schema inventory into domain-owned,
reviewable migration waves and supplies a fail-closed off-site Restic verifier.

## Current evidence

The isolated enterprise staging database is at `0034_wave2_event_governance`.
It contains 92 public tables including `alembic_version`: 91 application tables,
11 fully governed tables, one root-scope exception (`iam_tenant`), and 79
migration candidates. This supersedes the earlier 83-table estimate; no table
was altered to obtain the corrected count.

## Migration rules

1. A domain owner must identify authoritative tenant, workspace, and actor data.
2. `DERIVED_SAFELY` requires a declared foreign-key path and orphan count zero.
3. `REQUIRES_BACKFILL` requires deterministic SQL, before/after counts, and a
   rollback strategy. Placeholder UUIDs and generic actors are prohibited.
4. Nullable expansion precedes bounded backfill. Foreign keys, uniqueness,
   checks, and `NOT NULL` are added only after validation.
5. Each wave runs forward, rollback, and second-forward against a restored copy,
   followed by tenant/workspace isolation, query-plan, regression, and exact-head CI.
6. Immutable event/audit/history tables use `NOT_APPLICABLE` for soft deletion;
   append-only enforcement remains authoritative.
7. No later wave starts while an earlier wave contains an unapproved backfill.

## Waves and authority

- Wave 1: Identity Owner — tenant/workspace/identity tables.
- Wave 2: Integration Platform Owner — command/event/workflow/outbox/audit.
- Wave 3: Odoo Business Owner — campaigns, leads, Odoo acknowledgements and reconciliation.
- Wave 4: Communications Owner — notifications, recordings, telephony and VICIdial.
- Wave 5: AI Platform Owner — AI memory, knowledge and tools (no current tables).
- Wave 6: Commercial Owner — commercial usage and billing (no current tables).
- Wave 7: Security Data Owner — reporting, security, quarantine and miscellaneous legacy data.

The generated inventory is `legacy-governance-inventory.json`; the concise
wave manifest is `legacy-governance-waves.json`. Neither file contains row data
or credentials.

## Off-site Restic gate

`scripts/validate_offsite_restic.sh` requires root-owned mode `0600` repository,
password, and either SSH-key or S3 credential files. S3 validation explicitly
disables cloud-metadata credential fallback. It validates a caller-supplied encrypted archive
and checksum, proves repository access, uploads a real snapshot, lists it,
runs repository data checks, restores that exact snapshot, and verifies its
checksum. It prints no repository value or secret.

The gate remains blocked until the approved files exist and the script succeeds.

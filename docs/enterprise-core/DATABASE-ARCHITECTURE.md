# Enterprise database architecture baseline

## Recovery acceptance

Release acceptance requires one Alembic head, forward/one-revision
rollback/forward migration, an encrypted logical backup with a verified digest,
an isolated restore, and an exact-transaction PITR rehearsal. Plaintext is
removed after validation. Off-site protection is reported as passing only when
a configured remote target and its independent checksum are verified.

The schema audit reports legacy tables that predate current audit columns.
Retrofitting them requires a reviewed data migration; nullable placeholder
columns are not used to manufacture compliance.

## Migration waves

1. Identity, tenant, and workspace.
2. Command, event, workflow, and audit.
3. Odoo integration and business records.
4. Communications and telephony.
5. AI, memory, knowledge, and tools.
6. Commercial usage and billing.
7. Reporting, security, and legacy miscellaneous tables.

Each wave is independently reversible and must pass existing-data backfill,
forward/rollback/forward, tenant isolation, query-plan, and exact-head CI gates
before the next wave starts. `iam_tenant` is the root-scope exception: it does
not receive a self-referential tenant or workspace identifier.

PostgreSQL is the authoritative transactional store. Redis is a bounded cache
and notification accelerator; Qdrant stores embeddings only behind
middleware-enforced tenant and workspace filters. Applications receive no
direct database credentials.

New governed tables must use UUID primary keys, tenant and workspace scope,
created/updated timestamps and actors, a nullable deletion timestamp,
optimistic version, and an audit reference. Unique constraints include tenant
and workspace where identifiers are not globally unique. Foreign keys and
checks enforce lifecycle invariants.

Backups require encryption, checksums, least-privilege ownership, off-host copy
where configured, daily full plus hourly incremental/PITR coverage, and an
isolated restore rehearsal. No production restore is authorized by this PR.

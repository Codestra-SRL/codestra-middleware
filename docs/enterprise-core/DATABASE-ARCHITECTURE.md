# Enterprise database architecture baseline

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

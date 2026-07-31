# Middleware staging migration and rollback

1. Assert hostname `middleware` and database name `codestra_lead_staging`.
2. Reject names `postgres`, `production`, and `codestra`, and reject any DSN
   whose host is not the isolated compose service `middleware-postgres`.
3. Back up the empty/synthetic database, encrypt it outside the container, and
   verify its SHA-256 manifest.
4. Run `alembic current`, then `alembic heads`; require the sole head
   `0029_merge_lead_recording_heads`.
5. Run the profiled one-shot migration job and smoke tests. Never migrate via
   the long-running application container.
6. On failure, stop without starting Middleware, restore the verified backup
   into a fresh staging-only volume, and re-run `alembic current`.

No command in this document targets an existing database.

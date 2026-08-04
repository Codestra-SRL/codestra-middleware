# Redis middleware/n8n infrastructure contract

Secret-free source of truth for the validated Redis ACL, Compose mounts,
validation, monitoring, and recovery contract. Runtime passwords and ACL
hashes are deployment-local and are never committed.

Validated runtime: Redis 7.4.5, private networking, AOF persistence,
`noeviction`, disabled default user, `middleware-service`, `n8n-service`, and
protected `redis-recovery` identity. The active source paths and backup
locations are recorded in the evidence file.

Render deployment-local secrets at apply time, validate `docker compose config`,
apply one service group at a time, and use the runbooks for rollback. Durable
outbox, command, dead-letter, and audit state remains in PostgreSQL.

# n8n failure and recovery

Retry is restricted to network interruption, timeout, HTTP 408/429, and
502/503/504. Schema, authentication, authorization, routing, tenant, and
payload conflicts are permanent. Full-jitter exponential backoff is bounded at
60 seconds and attempts at eight (five by default).

Executions transition through `PENDING`, `DISPATCHING`, `RUNNING`, `COMPLETED`,
`FAILED`, `RETRY`, `DEAD_LETTER`, `CANCELLED`, and `TIMED_OUT`. PostgreSQL
persists every recovery-relevant value. Redis restart therefore cannot lose a
job. Middleware restart resumes `PENDING`/`RETRY`; n8n queue mode resumes from
its PostgreSQL/Redis queue configuration. Exhausted jobs remain durable dead
letters with hashes and safe failure codes.

Circuit breakers for n8n, Odoo, AI providers, and VICIdial may use expiring
Redis counters, but incident/audit evidence remains durable.

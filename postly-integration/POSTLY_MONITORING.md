# Postly monitoring

Existing monitoring covers public HTTPS and `/auth`, TLS, host resources, disks/inodes, containers/restarts, PostgreSQL, Redis, Temporal, Elasticsearch, media storage, backup result/age, and worker health without publishing private exporters. Labels are `site=postiz`, `domain=social.codestra.co`, `server=49.12.145.107`, `environment=production`, and service.

Integration activation must add Middleware-owned metrics: schedule attempts/results by safe category, publishing failures, idempotency conflicts, reconciliation backlog/age, callback auth/replay failures, and provider latency. Labels must never contain captions, account handles, emails, tokens, campaign names, or external post content.

Alertmanager delivery remains a known operational blocker until a real receiver and recovery-notification test are configured. Do not create a false-success test receiver. Suggested alerts: backlog oldest >15 minutes warning/>60 critical, publication failure rate >5% for 15 minutes, callback auth failure >0, and duplicate conflict spike.

# Rollback

Pause AI outbox delivery and disable all AI flags. If a migration rollback is required, take a database backup first and use the repository migration downgrade in an isolated rehearsal before production. Do not delete job, audit, or result history.

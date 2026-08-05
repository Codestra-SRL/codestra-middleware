# Rollback validation

Rollback is a controlled operation with an authorized owner, rehearsed target
version, verification reference, bounded impact statement, and audit record.
Application/configuration/feature-flag rollback may be prepared through the
release process. Database, carrier, trunk, and destructive data rollback are
never automatic and require explicit governance approval.

Rollback validation proves the target artifact exists, backups are readable,
the procedure was rehearsed in staging, health checks are defined, and the
post-rollback acceptance test is recorded.

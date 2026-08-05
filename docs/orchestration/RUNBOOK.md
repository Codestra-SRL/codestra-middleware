# Runbook

On Redis loss, rely on PostgreSQL outbox; on worker failure, expire leases and requeue
safe work; on duplicate or mismatch, stop external writes and reconcile.

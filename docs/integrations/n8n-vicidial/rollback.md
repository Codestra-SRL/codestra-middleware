# Rollback

1. Disable the master production switch and all provider/callback switches.
2. Deactivate affected n8n workflows.
3. Stop dispatch workers without deleting durable records.
4. Preserve command, event, delivery, and audit history.
5. Restore the last verified image and migration state using deployment backups.
6. Reconcile pending commands and dead letters before reactivation.

Never flush Redis or delete unknown keys as a rollback mechanism. Provider databases are not modified by rollback.

# Staging rollback plan

Keep all flags false, stop staging application containers, preserve sanitized
logs, and restore only checksum-verified staging backups into newly created
staging volumes. Verify database identity, the sole Alembic head, Odoo module
state, inactive workflow state, disabled binding, and zero unexpected activity
before declaring rollback complete. Never attach or restore into an existing
volume or database.

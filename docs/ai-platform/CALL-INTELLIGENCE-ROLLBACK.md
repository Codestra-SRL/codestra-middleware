# Rollback

Disable all Call Intelligence processing and Odoo flags first; keep workflows inactive. Stop workers, preserve audit records, and restore application/database snapshots only under the existing controlled restore procedure. Migration downgrade removes only Call Intelligence tables and is destructive, so it requires owner approval. AI rollback pins the previous immutable image digest; never reuse evidence from another digest.


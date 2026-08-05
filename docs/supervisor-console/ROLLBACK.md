# Rollback

Before staging, snapshot middleware PostgreSQL, current image/Compose/Caddy/RBAC/flags and frontend artifact hashes. Roll back frontend and middleware artifacts, downgrade exactly one revision, verify prior migration head and health, and remove synthetic supervisor rows. Never restore production during this mission.

# Backup and restore

Encrypted Restic repository: `/srv/codestra-platform/backups/restic-repository`, outside Postly volumes. Latest verified snapshot at preparation time: `8b16ff1e`; `LAST_SUCCESS=2026-08-02T19:02:25Z`. The database dump SHA-256 is `9356b3ef2863ef5dc2c73b894454a7b42502d4f7257b0f2fbd11feed6743e374`; its catalog contains 432 entries. The repository password remains in its owner-only secret file and is not documented here. Off-server redundancy remains required.

The backup includes PostgreSQL and Temporal logical dumps, media/config volumes, Compose and Caddy configuration, encrypted environment material, container/image/volume/network inventories, migration/release metadata, monitoring and firewall configuration. The PostgreSQL dump catalog was listed and restored into an isolated database; 69 tables and baseline counts were verified.

Use `/srv/postiz/backups/run-backup.sh` and verify the service exit status, `LAST_SUCCESS`, Restic snapshot, checksums, and dump catalog. Restore only into uniquely named disposable containers/networks first. Never overwrite production until rollback authority approves and the application is stopped. Full procedure: `/srv/postiz/documentation/rollback.md`.

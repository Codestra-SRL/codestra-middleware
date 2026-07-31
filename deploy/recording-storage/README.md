# Private recording object storage

This source-only deployment binds the S3 API to Server A's private address,
does not publish the MinIO console, requires TLS and KES-backed encryption, and
creates the recording bucket with versioning and governance object lock.

Root credentials are external bootstrap secrets. Applications use separate
`recording-middleware-write`, `recording-middleware-read`,
`recording-retention-worker`, and `recording-backup-auditor` identities.
Server B receives only a short-lived, one-object upload reservation.

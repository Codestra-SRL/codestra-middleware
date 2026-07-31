# Private recording object storage

This source-only staging deployment binds the S3 API to Server A's private
address, does not publish the MinIO console, requires TLS, and configures
bucket-default SSE-S3 encryption. MinIO uses one staging deployment encryption
key through KES for SSE-S3. The bucket is created with versioning and
governance object lock.

The bootstrap script rejects any environment other than `staging` and any
encryption mode other than `SSE-S3`. Production external-KMS configuration is
not included and remains blocked pending a separate approval.

```text
STAGING_ENCRYPTION_MODE=SSE_S3
PRODUCTION_EXTERNAL_KMS_GATE=BLOCKED
```

Root credentials are external bootstrap secrets. Applications use separate
`recording-middleware-write`, `recording-middleware-read`,
`recording-retention-worker`, and `recording-backup-auditor` identities.
Server B receives only a short-lived, one-object upload reservation.

# Off-site Restic diagnosis — 2026-08-05

No credential value is recorded here.

## Root cause

The approved Backblaze B2 destination uses its S3-compatible endpoint. The
timed-out invocation supplied B2-native environment names, so the S3 client did
not receive credentials and attempted cloud-instance metadata at
`169.254.169.254:80`. This was the timeout source; DNS and the public route were
healthy. The bounded probe was terminated without changing repository state.

The corrected read-only invocation maps the protected files to the AWS/S3
credential variables and sets `AWS_EC2_METADATA_DISABLED=true`.

## Read-only validation

```text
START_UTC=2026-08-05T14:35:15Z
END_UTC=2026-08-05T14:35:18Z
OFFSITE_REPOSITORY_REACHABLE=PASS
SNAPSHOT_LIST=PASS
SNAPSHOT_COUNT=2
LATEST_SNAPSHOT=6fc0c505
```

A complete repository data check and isolated restore of that existing snapshot
also passed:

```text
START_UTC=2026-08-05T14:36:17Z
END_UTC=2026-08-05T14:36:26Z
SNAPSHOT_CHECK=PASS
ISOLATED_EXISTING_SNAPSHOT_RESTORE=PASS
RESTORED_FILE_COUNT=432
RESTORED_BYTES=3361508
```

## Remaining scope blocker

The destination authorization and existing snapshots are bound to change
`O19-B1-INDEPENDENT-BACKUP` and Odoo 19 release material. They do not authorize
uploading the current enterprise-core Middleware backup. Consequently this
work does **not** claim `BACKUP_UPLOAD=PASS` or current Middleware off-site
restore/checksum proof.

Required external action: approve the current Middleware encrypted backup for
this repository/prefix, or provide the separately approved Middleware Restic
repository and protected credential files. After that, run
`scripts/validate_offsite_restic.sh` with the encrypted archive and its checksum.

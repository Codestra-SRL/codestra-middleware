# Social Operations Console API

The `/api/v1/ops/social` foundation exposes configuration and tenant-scoped dead-letter views. Permissions are distinct: `social.ops.read`, `social.ops.retry`, `social.ops.deadletter`, `social.ops.accounts`, `social.ops.campaigns`, and `social.ops.security`.

Responses are allowlisted and exclude tokens, raw secrets, filesystem paths, post bodies and raw provider payloads. Replay remains disabled; unknown-after-send provider publish work is never replay-eligible without reconciliation.

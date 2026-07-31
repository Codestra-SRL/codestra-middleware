# Recording Retryability Contract

Retries preserve the original `recording_uid`, environment, payload, object
version binding, and idempotency key. A retry must not create a second recording
or silently replace an object version.

| Condition | Retryability | Required behavior |
|---|---|---|
| Network timeout, connection failure, HTTP `429`, or HTTP `5xx` | Retryable | Exponential backoff with bounded jitter; reuse the same idempotency key. |
| Odoo unavailable after `SERVER_VERIFIED` | Retryable | Remain `SERVER_VERIFIED`; retry only the HMAC-authenticated metadata upsert. |
| Authentication failure, stale timestamp, replayed nonce, or HTTP `401`/`403` | Not automatically retryable | Refresh runtime credentials/configuration and use a new timestamp and nonce after operator correction. |
| Request-schema failure or HTTP `400`/`422` | Not retryable | Correct the contract defect; do not mutate the accepted reservation. |
| Idempotency payload conflict or HTTP `409` | Not retryable | Quarantine for review; never generate a new key to bypass the conflict. |
| Missing object immediately after upload | Retryable only within bounded consistency window | Re-check the same opaque identifier; never select a different object. |
| Checksum, size, content type, environment, campaign, UID, or version mismatch | Not retryable | Transition to `QUARANTINED`. |
| Optional n8n projection delivery failure | Retryable outside the critical path | Keep `ODOO_LINKED`; retry the flat allowlisted projection independently. |

Every Odoo attempt uses a new cryptographic nonce and current timestamp while
retaining the original idempotency key. Replay rejection is final for that
nonce, not for the business operation.

The n8n binding and workflow default to inactive. n8n delivery cannot block
reservation, verification, the Odoo upsert, the canonical acknowledgement, or
the `ODOO_LINKED` transition.

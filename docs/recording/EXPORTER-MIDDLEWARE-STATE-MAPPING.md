# Exporter–Middleware State Mapping

This mapping is the middleware interpretation of the recording v1 state
contract at PR A head `817299f2648be9b8c7c29ffd51645bf2e3a5a095`.

| Exporter observation | Middleware state | Required middleware action |
|---|---|---|
| Reservation accepted | `UPLOADING` | Return the same reservation response for the same environment and idempotency key. |
| Completion received | `UPLOADED` | Inspect the exact private object version; do not acknowledge verification yet. |
| Object metadata matches | `SERVER_VERIFIED` | Persist the version binding and attempt the canonical Odoo metadata upsert. |
| Canonical Odoo acknowledgement validates | `ODOO_LINKED` | Mark the Odoo link and optionally enqueue the flat n8n projection. |
| Object or completion binding conflicts | `QUARANTINED` | Reject the completion and require operator review; never retry as a new recording. |
| Terminal exporter/storage failure | `FAILED` | Preserve the failure code and immutable audit history. |

`RESERVATION_CREATED` is the initial internal audit state. The first successful
reservation transition is `UPLOADING`. A recording must never transition to
`ODOO_LINKED` from any state other than `SERVER_VERIFIED`, and it must never do
so from a partial, malformed, or mismatched Odoo acknowledgement.

The five core recording schemas remain authoritative and nested. The optional
n8n delivery uses only `recording-n8n-event-v1.json`; it is not a state
transition prerequisite and it never receives the nested core recording object.

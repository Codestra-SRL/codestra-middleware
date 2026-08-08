# Hootsuite capabilities

Advertised: account discovery, create/send, schedule, cancel/delete, status reconciliation, image, multi-image, video, and media upload initiation. Message update, comments/messages workflows, analytics, native idempotency, and verifiable native webhooks are not advertised because the reviewed publishing API reference does not establish those contracts.

Hootsuite message states normalize as: `SCHEDULED` to `SCHEDULED`, `SENT` to `PUBLISHED`, `PENDING_APPROVAL` to `REQUIRES_ACTION`, and rejection/permanent failure to `FAILED`.

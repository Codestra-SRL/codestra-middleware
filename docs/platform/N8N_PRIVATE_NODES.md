# Private n8n nodes

`integrations/n8n/nodes-codestra` contains the private `@codestra/n8n-nodes-codestra` package. It exposes EventTrigger, Social, Campaign, Lead, Odoo, AI, Analytics, Audit, Notification, DeadLetter, Approval and Media nodes.

All nodes use one Middleware credential, HTTPS, bearer service identity, timestamped HMAC, nonce, correlation ID and optional idempotency key. They never accept provider tokens or direct provider/CRM endpoints. The package is private and must not be published to a public registry.

The Phase N5 implementation supplies the source-managed request/signing and node contract foundation. Installing it into production n8n is a separately gated artifact-promotion step.

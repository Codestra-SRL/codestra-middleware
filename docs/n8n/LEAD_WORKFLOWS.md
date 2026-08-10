# Lead workflows

Four inactive Git-controlled workflows are supplied: `CdstIdentityResolveV1`, `CdstLeadIntelligenceV1`, `CdstNextBestActionV1`, and `CdstAttributionUpdateV1`. They use the private Codestra node contracts and call Middleware; no identity, consent, revenue, or action state is canonical in n8n.

Every workflow includes manifest metadata, audit/result callback, and dead-letter paths. The next-action workflow recommends only. Odoo operations remain Middleware dry-run projections. Promotion requires exact Git SHA, workflow validation, isolated staging tests, and separate activation approval.

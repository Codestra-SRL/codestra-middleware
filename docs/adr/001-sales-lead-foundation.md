# ADR 001: Governed sales lead foundation

Status: Accepted for Phase 1 (development and staging only)

## Decision

The only permitted flow is `scraper -> authenticated middleware intake -> strict validation -> deterministic identity resolution -> tenant-bound Odoo read-only lookup -> compliance/suppression evaluation -> dry-run result`.

Odoo 19 remains the authoritative CRM and business record. Middleware is the only cross-system operational gateway. n8n may orchestrate asynchronously but is not authoritative. The scraper must never write to Odoo, n8n, VICIdial, or a VICIdial database. Phase 1 performs no Odoo mutation, VICIdial publication, outreach, provider-paid call, or live workflow activation.

Identity, consent, DNC, and suppression decisions are deterministic, tenant-bound, policy-versioned, and auditable. AI is restricted to non-authoritative public-evidence summarization, service/industry classification, and lead-fit explanation. It cannot invent contact data, establish identity or consent, override a compliance gate, or authorize outreach.

An authoritative lookup failure fails closed: the candidate is not classified as net new. Possible duplicates create a review record and never merge into Odoo.

## Consequences

All write and publication flags remain false. Phase 2 may add a durable repository and real read-only Odoo transport behind these ports, but enabling writes or outreach requires a separate architecture and governance decision.

# Phase N8 system canary

Phase N8 certifies the internal business pipeline with reserved synthetic data. It does not certify a real Postly account, production Odoo, VICIdial, or any contacting action.

The executable acceptance test is `tests/integration/test_phase_n8_system_canary.py`. It creates a unique tenant, campaign, content item, event, person, lead, two campaign touches, and a synthetic USD revenue event in disposable PostgreSQL. The test drives the durable n8n delivery bridge, simulates an authenticated successful workflow result at the established execution boundary, and verifies terminal reconciliation.

The canary enables identity, lead intelligence, next-action, attribution, revenue-sync, and social n8n flags only in the disposable process. Source and production defaults remain off. `SOCIAL_PUBLISH_ENABLED`, `SOCIAL_ODOO_WRITE_ENABLED`, VICIdial writes, and automatic contacting remain false.

## Certified path

```text
synthetic social.message.received
  -> IntegrationEvent / IntegrationDelivery
  -> governed n8n execution bridge
  -> canonical person and contact-point resolution
  -> campaign-scoped lead deduplication
  -> consent and DNC policy
  -> explainable score and next action
  -> Odoo dry-run projection
  -> immutable campaign touches
  -> explicitly synthetic revenue event
  -> five versioned attribution calculations
```

The n8n portion exercises middleware staging, idempotency, execution creation, and completion reconciliation. It does not claim that the inactive Git-controlled N7 lead workflows were promoted to the shared n8n service.

## Acceptance invariants

- Synthetic revenue carries `is_synthetic=true` and is excluded from ordinary aggregate attribution views.
- A repeated provider event produces one canonical integration event and delivery.
- Matching uses hashed normalized email/phone values and a tenant-scoped social identity.
- Unknown consent produces `MANUAL_REVIEW`; confirmed DNC and spam produce `DO_NOT_CONTACT`.
- No action recommendation dispatches contact.
- Odoo projection returns `dry_run=true`, `write_enabled=false`, and `command_dispatched=false`.
- Redis is not canonical; PostgreSQL records survive queue interruption.
- No production account, customer record, or revenue record is used.

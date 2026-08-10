# Phase N8 system canary

Phase N8 certifies the internal business pipeline with reserved synthetic data. It does not certify a real Postly account, production Odoo, VICIdial, or any contacting action.

The database acceptance test is `tests/integration/test_phase_n8_system_canary.py`. The runtime acceptance command is `scripts/run_phase_n8_http_canary.py`. It creates a unique tenant, campaign, content item, event, person, lead, campaign touch, and synthetic USD revenue event in disposable PostgreSQL. The runtime command drives the durable delivery bridge through an authenticated HTTP webhook in an isolated n8n instance and requires the actual signed workflow callback before terminal reconciliation succeeds.

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

The n8n workflow remains inactive in Git and is rendered by `scripts/render_phase_n8_n8n_workflow.py`. Operators may import and publish it only in an isolated staging instance. The webhook acknowledges immediately so middleware can release its execution-row lock before the workflow calls the signed authorization boundary.

Every identity resolution, lead creation/deduplication, interaction, next-action decision, synthetic revenue event, and attribution calculation appends a tenant-sequenced SHA-256 hash-chain record to `lead_pipeline_audit_events`. PostgreSQL triggers reject updates and deletes. Audit metadata is allowlisted and excludes raw contact values.

## Acceptance invariants

- Synthetic revenue carries `is_synthetic=true` and is excluded from ordinary aggregate attribution views.
- A repeated provider event produces one canonical integration event and delivery.
- Matching uses hashed normalized email/phone values and a tenant-scoped social identity.
- Unknown consent produces `MANUAL_REVIEW`; confirmed DNC and spam produce `DO_NOT_CONTACT`.
- No action recommendation dispatches contact.
- Odoo projection returns `dry_run=true`, `write_enabled=false`, and `command_dispatched=false`.
- Redis is not canonical; PostgreSQL records survive queue interruption.
- No production account, customer record, or revenue record is used.

# Wave 3 Odoo business integration

Wave 3 adds a durable, disabled-by-default boundary between Codestra clients and
Odoo. It does not copy Odoo business records and does not enable an Odoo write.

## Ownership

Odoo owns customers, companies, contacts, leads and CRM records, activities,
appointments, projects and tasks, support records, calls and callbacks,
commercial and marketplace references, subscriptions, invoices, and other
business records.

Middleware owns commands, immutable event history, outbox/delivery state,
approval, idempotency, retries, leases and fencing, reconciliation state,
privacy-safe audit metadata, and AI execution state.

The only supported flow is `browser/AI -> Middleware -> Odoo adapter`. Browser
and AI clients cannot select an Odoo model, database, or record ID. The
production adapter remains disabled until a separate activation review verifies
the staging Odoo schema, routing identifiers, least-privilege service identity,
backup, monitoring, and bounded canary.

## Services

The shared command contract is exposed through named Customer, Lead, Activity,
Project, Appointment, Support, Voice, AI, Marketplace, Commercial, Usage, and
Reconciliation service boundaries. Supported resource types include all Wave 3
modules: customer/company/contact, lead/CRM, activity, appointment,
project/task, support/SLA/customer health, call/callback/recording/transcript,
Voice AI/AI employees, marketplace/commercial/subscription/usage, documents,
knowledge, and audit.

## HTTP contract

All routes require validated OIDC identity and server-side permissions. Tenant
and workspace come only from validated token claims.

| Method | Path | Permission | Behavior |
|---|---|---|---|
| GET | `/api/v1/business/resource-types` | `business.read` | Contract discovery |
| POST | `/api/v1/business/commands` | `business.write` | Durable idempotent command |
| GET | `/api/v1/business/commands` | `business.read` | Tenant/workspace command list |
| GET | `/api/v1/business/commands/{id}` | `business.read` | Scoped command status |
| POST | `/api/v1/business/commands/{id}/approval` | `business.approve` | Exact approval decision |
| POST | `/api/v1/business/commands/{id}/cancel` | `business.write` | Cancellation request |
| POST | `/api/v1/business/reconciliations` | `business.reconcile` | Durable reconciliation request |

Command creation requires `Idempotency-Key` and `X-Correlation-ID`. Payloads
are limited to 128 KiB and reject privileged routing and secret-bearing fields.
Archive and transition operations require explicit recorded approval. API
responses expose middleware public IDs and hashes, never Odoo database or
record identifiers.

## Delivery and recovery

`delivery_mode=DISABLED` is the schema and application default. Atomic workers
use `FOR UPDATE SKIP LOCKED`, bounded leases, monotonically increasing fencing
tokens, bounded exponential retry, dead letters, cancellation checks, and
expired-lease recovery. Reconciliation uses a separate leased queue. Odoo
references are recorded only after a fenced delivery succeeds.

## Rollback

Migration `0035_odoo_business` can be rolled back to
`0034_wave2_event_governance` in disposable and pre-activation environments.
Once real delivery is separately authorized, application rollback should retain
the forward-compatible schema and its command/audit history.

## Activation prerequisites

- Approved Odoo staging URL, database identity, schema and routing evidence.
- Least-privilege credential stored as a protected server-side secret reference.
- Synthetic staging contract, duplicate-prevention, reconciliation and rollback tests.
- Monitoring and alert recovery evidence.
- Independent owner authorization for a bounded canary.

Until then, Odoo delivery and all business writes remain disabled.

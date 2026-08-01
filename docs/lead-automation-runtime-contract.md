# Lead Automation Runtime Contract

This document is the source-of-truth matrix for the Server A staging lifecycle.
`IntegrationEvent` is the canonical event journal. Compatibility ingress rows and
transport outbox rows must be created in the same transaction and linked to it.

| Component | Operation | Canonical endpoint | Authentication | Request schema | Response schema | Event ID | Correlation ID | Idempotency | Originating outbox | Retry policy | Terminal failure route |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Odoo | Create immutable producer record | model method `codestra.integration.outbox.create_event` | Odoo ACL and internal capability | `OdooLeadAutomationEventV1` | immutable outbox row | `event_uuid` | `correlation_id` | `(environment,idempotency_key)` unique | `event_uuid` | producer-owned, bounded | Odoo outbox `dead_letter` |
| Middleware | Odoo event ingress | `POST /api/v1/events/odoo` | protected bearer credential | `CanonicalEventEnvelopeV1` | `EventAcceptedV1` | `event_id` | `correlation_id` | `(source,idempotency_key)` unique | `originating_odoo_outbox_id` | no automatic ingress retry | HTTP conflict/rejection |
| Middleware | Durable event journal | database transaction | service role | `IntegrationEvent` + linked `EventInbox` + linked `OutboxEvent` | committed rows | `original_event_id` | immutable `correlation_id` | unique `idempotency_key` per source/environment | immutable `originating_odoo_outbox_id` | transport outbox, max 5 | transport dead letter |
| n8n | Verify dispatched event | `POST /api/v1/automation/events/verify` | protected n8n credential plus dispatcher HMAC | `N8nVerificationRequest` | verified canonical event | `event_id` | `correlation_id` | `idempotency_key` | both immutable outbox IDs | none | `CdstErrorDeadLetterV1` |
| Middleware | Fetch canonical context | `GET /api/v1/integration/events/{event_id}/context` | protected n8n credential | path event ID | `CanonicalEventContextV1` | `event_id` | `correlation_id` | `idempotency_key` | both immutable outbox IDs | timeout 10s, no workflow retry | bounded workflow failure |
| Middleware | Register n8n execution | `POST /api/v1/n8n/executions` | protected n8n credential | `ExecutionRegistrationV1` | `ExecutionRegistrationResultV1` | `event_id` | `correlation_id` | registration hash and `(event_id,workflow_key)` unique | database-derived | caller bounded, duplicate-safe | conflict or failure endpoint |
| Middleware | Record internal hot-lead result | `POST /api/v1/n8n/internal-results` | protected n8n credential | `InternalHotLeadResultV1` | accepted internal result | `event_id` | `correlation_id` | `idempotency_key` | database-verified | none | failure endpoint |
| Middleware | Acknowledge execution | `POST /api/v1/n8n/acknowledgements` | protected n8n credential | `AcknowledgementV1` | durable acknowledgement | `event_id` | `correlation_id` | acknowledgement hash | database-derived | duplicate-safe | failure endpoint |
| Middleware | Receive terminal result | `POST /api/v1/n8n/results` | protected n8n credential | `CanonicalResultEnvelopeV1` | durable result | `event_id` | `correlation_id` | unique `idempotency_key` | both IDs validated against stored event/outbox | duplicate-safe | `POST /api/v1/n8n/failures` |
| Middleware | Park terminal failure | `POST /api/v1/n8n/failures` | protected n8n credential | `CanonicalFailureEnvelopeV1` | terminal acknowledgement | `event_id` | `correlation_id` | unique failure key | both IDs validated against stored event/outbox | maximum 5 attempts | durable `DEAD_LETTERED` acknowledgement |
| Odoo | Apply Middleware result | `POST /api/v1/integration/results` | OAuth bearer with scoped service claims | `OdooIntegrationResultV1` | persisted/duplicate result | `event_id` | `correlation_id` | `result_public_id` and `acknowledgement_id` unique | `originating_outbox_public_id` resolved server-side | Middleware outbox, max 5 | Middleware transport dead letter |

## Invariants

- `IntegrationEvent.original_event_id`, `correlation_id`, `idempotency_key`,
  `environment`, and `originating_odoo_outbox_id` are immutable.
- `EventInbox.integration_event_id` and `OutboxEvent.integration_event_id` point
  to the same canonical event and are created in its transaction.
- The Middleware transport outbox UUID is generated before dispatch and included
  as `originating_middleware_outbox_id` in every n8n lifecycle call.
- Result and failure handlers resolve both outbox identities from stored rows and
  reject caller-supplied mismatches.
- `lead.hot` internal results never trigger email, SMS, calling, callbacks,
  VICIdial, social posting, or external lead distribution.
- Workflow error routes do not reference themselves; terminal failure submission
  is bounded and idempotent.

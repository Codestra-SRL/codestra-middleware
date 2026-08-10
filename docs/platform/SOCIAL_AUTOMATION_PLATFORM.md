# Codestra Social Automation Platform

Middleware is the canonical control plane. PostgreSQL owns campaigns, content versions, approvals, jobs, audit, delivery and trace links; Redis signals work; n8n executes provider-neutral workflows; provider and CRM adapters remain behind Middleware.

```text
Client -> Middleware APIs -> PostgreSQL -> outbox/Redis -> n8n private nodes
                                             |               |
                                             |               `-> signed result callback
                                             `-> provider-neutral workers -> provider
```

The N5 source defaults publish nothing. Provider failover, dual publish, automatic approval, automatic dead-letter replay, and Odoo writes are forbidden. Current workflows are inactive source artifacts intended for synthetic staging validation.

## Invariants

- n8n never owns canonical business state or provider credentials.
- Every state mutation is tenant-scoped, permission-gated, correlated and audited.
- Approved content is immutable by version; scheduling refers to an exact approved version.
- AI output is untrusted advice and cannot override approval, consent, DNC or provider safety gates.
- Health scores inform operators and never trigger provider failover.

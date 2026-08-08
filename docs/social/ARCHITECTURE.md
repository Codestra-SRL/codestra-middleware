# Architecture

```text
Clients / Odoo / n8n / AI
          |
          v
Codestra Social API -> SocialPublishingService -> SocialProviderRegistry
                              |                    |-> Postly adapter -> Postiz client
                              |                    `-> Hootsuite adapter (disabled)
                              v
                 PostgreSQL job/outbox -> Redis signal -> worker
                              |
                              v
                normalized IntegrationEvent -> n8n / disabled Odoo projection
```

PostgreSQL is authoritative. Redis carries only job identifiers. Provider adapters translate authentication, requests, statuses, errors and webhooks. No AI content-generation logic belongs in an adapter.

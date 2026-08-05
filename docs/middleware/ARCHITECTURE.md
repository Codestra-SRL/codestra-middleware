# Middleware platform architecture

The middleware is the only authorized boundary between users, business services,
AI runtimes, workflows, Odoo, n8n, voice, marketplace, and external providers.
Requests carry tenant, workspace, actor, correlation, trace, authorization, and
idempotency context. Direct service-to-service writes are prohibited.

The enterprise foundation stores service registry, feature-flag, command, and
event metadata in PostgreSQL. Production mutations and external dispatch remain
disabled until separately approved.

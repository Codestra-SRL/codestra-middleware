# Redis persistence

Workflow/control durability is PostgreSQL-backed. Temporary voice/events/integration
keys require TTL and approved eviction. No eviction is allowed for durable queue state.

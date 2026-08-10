# Revenue events

Revenue events cover opportunity creation, appointment booking, won sales, payments, subscriptions, refunds, and cancellations. Monetary values must come from an authoritative source and require an ISO currency. Tenant, source system, and hashed external reference provide durable idempotency.

Repeated external events return the existing Codestra UUID. Raw external identifiers are not exposed in normal APIs or metrics.

# Odoo normalized result contract

Middleware mutations originate only from the durable result outbox and terminate at `POST /api/v1/integration/results`. Each request binds tenant, business unit, campaign, originating event, aggregate, schema version, payload hash, optimistic business version, idempotency key, correlation, causation, request ID, timestamp, and trace context.

Result types map to explicit service handlers and field allowlists. Payloads never select a model, table, SQL, method, arbitrary field, URL, or expression. Odoo compliance, DNC, suppression, manual locks, and newer business versions override stale middleware intent. Same key/hash returns the prior result; changed payload returns conflict; concurrent delivery creates one logical mutation.

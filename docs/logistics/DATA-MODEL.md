# Data model

All operational tables use stable public/external keys and tenant/workspace uniqueness. Orders, shipments, loads, stops, events, proof, exceptions, claims, quotes, audit, idempotency, and reconciliation live in PostgreSQL. Odoo stores accounting/customer projections, not high-frequency tracking events.

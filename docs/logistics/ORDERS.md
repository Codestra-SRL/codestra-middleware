# Orders

Transitions are `DRAFT → QUOTE_PENDING → QUOTED → APPROVED → BOOKED`; rejection and cancellation are explicit terminal paths. Every mutation is authenticated, scoped, idempotent, and audited.

# Synthetic attribution canary

Phase N8 creates two immutable synthetic campaign touches and one idempotent `PAYMENT_RECEIVED` event for USD 1,000 with `source_system=SYNTHETIC_TEST` and `is_synthetic=true`.

FIRST_TOUCH, LAST_TOUCH, LINEAR, POSITION_BASED, and TIME_DECAY calculations each persist a versioned calculation and allocations whose weights equal exactly one and whose attributed amounts equal the source amount. Recalculation supersedes the previous calculation version without deleting it.

Synthetic revenue is deliberately excluded from the normal campaign, content, network, provider, and lead aggregate queries. It therefore cannot contaminate production revenue reporting. The canary validates allocation mechanics, not actual revenue.

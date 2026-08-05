# Idempotency

PostgreSQL is authoritative. Redis may reserve short-lived keys. Hash mismatches are
conflicts; completed requests return their original result.

# Idempotency

Mutations require a unique idempotency key. Replays return the original operation/result and never call an external adapter twice.

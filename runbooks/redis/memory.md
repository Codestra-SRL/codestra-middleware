# Memory pressure

Check memory, fragmentation, evictions, and queue depth. Redis uses
`noeviction`; do not trade away idempotency or nonce safety. Pause workers with
the approved kill switch while capacity is restored.

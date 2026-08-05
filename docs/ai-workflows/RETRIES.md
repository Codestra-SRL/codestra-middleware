# Retries

Retries use classification, bounded exponential backoff, deterministic jitter, deadlines, circuit breakers, and dead letters. Tasks permit at most five retries and twenty tool calls. Completed irreversible actions are never rerun.

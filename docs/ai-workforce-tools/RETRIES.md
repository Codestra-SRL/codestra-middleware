# Retries

Only classified transient errors retry, with bounded exponential backoff, jitter, deadline, and maximum attempts. Policy and permission failures never retry.

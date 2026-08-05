# Retries

Only bounded transient failures retry with jitter and persisted schedules. Policy,
authorization, suppression, signature, and schema errors are final.

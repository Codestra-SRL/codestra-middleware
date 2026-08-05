# Canary rollback

Rollback restores the pre-canary feature-flag snapshot, inactive campaign and
staging list state, empty hopper, inactive n8n workflows, and prior registry
configuration. It does not delete audit records or accepted results. This
repository-only implementation has not performed a runtime rollback because
the assigned servers are inaccessible.

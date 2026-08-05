# Automatic stop gates

The middleware stops new work, preserves in-flight state, opens an incident, reconciles, restores the prior limit and runs integrity checks when a dangerous observation is detected. Stop gates are server-side and cannot be bypassed by the UI or n8n.

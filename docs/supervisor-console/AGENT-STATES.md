# Agent states

Canonical states are READY, ON_CALL, PAUSED, WRAP_UP and UNAVAILABLE. Events carry source sequence, event time, agent key, team key and tenant/workspace scope. State duration is derived from ordered events; conflicting or stale sequences are quarantined.

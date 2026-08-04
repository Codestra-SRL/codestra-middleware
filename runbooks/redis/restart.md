# Restart and reconnection

Restart Redis only in a controlled window after recording rollback. Verify
persistence, middleware reconnect, n8n reconnect where queue mode is enabled,
and synthetic-key cleanup before closing the change.

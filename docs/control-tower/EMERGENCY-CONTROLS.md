# Emergency controls

Pause controls require privileged role, MFA, reason, scope, approval where required, incident creation, idempotency, and no automatic re-enable. Supported intent states are `PAUSE_NEW_WORK`, `PAUSE_ALL_WORK`, `REVOKE_TOOLS`, `READ_ONLY`, and `SHUTDOWN`. The `/api/v1/control-tower/emergency-controls` endpoint is fail-closed and records an approved intent without directly changing runtime state; execution remains an operator-controlled action.

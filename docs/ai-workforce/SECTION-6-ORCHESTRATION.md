# Section 6 — AI Workforce Orchestration

Middleware is authoritative for AI employee, department, team, goal, task,
approval, tool-permission, workflow, retry, and audit state. n8n executes only
an approved workflow version after middleware authorization. Redis is temporary
coordination state; PostgreSQL remains the durable record.

Dispatch requires tenant and workspace context, an active employee/department/
goal, an allowlisted permission, an approved workflow, a unique idempotency key,
and human approval when the policy requires it. The dispatch endpoint is
fail-closed and reports intent only; it does not call n8n, Redis, or an external
adapter directly.

Goals and teams are durable, tenant/workspace-scoped records. Task records carry
goal/team references and workflow identity. Emergency states (`PAUSE_NEW_WORK`,
`PAUSE_ALL_WORK`, `REVOKE_TOOLS`, and `SHUTDOWN`) block new dispatches. Retry
classes are bounded and non-retryable authorization, policy, suppression, and
validation failures are not retried. Dead-letter replay remains approval-only.

Production AI employee activation, autonomous messages, financial actions,
telephony, trading, destructive actions, and self-modification remain disabled.

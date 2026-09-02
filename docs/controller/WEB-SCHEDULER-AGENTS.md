# Controller Web, Scheduler, Odoo, and n8n candidate

This candidate keeps the Controller API on its separate private entrypoint. It
does not mount Controller routes in the public Middleware application.

## Boundaries

- Web agent: `spiffe://codestra.internal/agent/web` at `10.40.0.3:9443`.
- Odoo and n8n capabilities are represented by typed Controller tools on the
  Server A agent. They do not call Qwen and contain no credential-management,
  administration, deletion, or database tools.
- Odoo mutation-like capabilities produce proposals only. Live Odoo delivery
  remains controlled by the existing disabled delivery flags.
- n8n execution is represented as a proposal only. Workflow activation and
  direct Qwen, LiteLLM, or Ollama access are not provided.
- Qwen and VICIdial agent profiles receive no Controller development tools.

## Scheduler

The policy engine supports priority, bounded attempts and timeout, queueing,
exclusive leases, heartbeats, exponential retry delay, expired-lease recovery,
dead letters, suspension, resumption, cancellation, audit chaining, and signed
verification evidence. Migration `0032_controller_scheduler` supplies the
durable PostgreSQL schema for tasks, approvals, audit, and verification.

The Controller remains an inactive candidate. Production deployment requires
a separately reviewed PostgreSQL repository adapter so the API uses these
tables rather than the current in-process candidate store.

## Activation blockers

Server C must install and activate its reviewed private agent with the issued
certificate. A real Controller-to-Web mTLS acceptance run must then prove the
positive flow and the raw-shell, wrong-tool, wrong-workspace, replay, expiry,
SPIFFE, server, and tenant denials. No live business integrations may be used
for that test.

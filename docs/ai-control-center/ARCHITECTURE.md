# Codestra AI Control Center architecture

The Control Center is a permission-aware administrative client. Browser
requests terminate at middleware; the browser never connects to Qwen, Qdrant,
n8n, Odoo, VICIdial, scraper storage, or Postiz directly. Middleware remains
authoritative for commands, approvals, audit and feature flags.

The current repository adds safe aggregation endpoints and a fail-closed
frontend shell. Runtime server connectivity remains unverified until approved
SSH access is available.

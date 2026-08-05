# Supervisor Console architecture

The browser authenticates with Codestra identity and calls middleware only. Middleware validates issuer, audience, expiry, authorized party, tenant, workspace, roles, teams and campaigns before querying PostgreSQL operational read models. VICIdial, Odoo, n8n, recordings and Qwen remain behind allowlisted adapters. PostgreSQL is durable truth; Redis may accelerate SSE delivery only.

Production is disabled. Agent and campaign commands, recording access, live dialing, monitoring audio, whisper and barge-in are disabled.

Server assignments: `65.109.65.169` owns the console and middleware; `5.9.108.250` owns private AI/Agent Assist; `49.12.145.107` is health-only; `65.21.67.207` is the VICIdial/Asterisk event source.

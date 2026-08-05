# Omnichannel support architecture

Server A (`65.109.65.169`) owns tenant-scoped tickets, conversations, routing, SLA, assignments, escalations, audit, and reconciliation; Odoo remains the authoritative support business record. Server B (`5.9.108.250`) provides private support AI. Server C (`49.12.145.107`) provides chat/social connectors and health checks. Server D (`65.21.67.207`) provides narrowly scoped voice-support events.

Real channels, automatic replies, and production notifications remain disabled.

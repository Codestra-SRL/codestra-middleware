# Codestra Logistics Architecture

Browser and driver clients call the Codestra middleware only. PostgreSQL owns lifecycle state; Odoo remains authoritative for customers and accounting. n8n is an inactive, idempotent orchestration adapter. AI, mapping, messaging, and telephony are private adapters and cannot execute dispatch, pricing, claims, or customer contact autonomously.

Zones: `65.109.65.169` control plane; `5.9.108.250` private AI; `49.12.145.107` public tracking proxy only; `65.21.67.207` call-support read adapter only.

# Developer Platform architecture

Server A (65.109.65.169) owns public API policy, tenant applications, OAuth/API credentials, webhooks, sandbox records, analytics and audit. Server B (5.9.108.250) exposes only middleware-mediated AI APIs. Server C (49.12.145.107) hosts documentation/assets and health only. Server D (65.21.67.207) provides allowlisted read-only telephony APIs.

Browsers and developers never access databases or internal services directly.

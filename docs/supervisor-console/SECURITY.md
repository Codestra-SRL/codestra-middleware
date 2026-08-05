# Security

JWT validation requires signature, issuer, audience, expiry and authorized party. Identity and scope derive only from validated claims. APIs enforce tenant/workspace/team scope, deny IDORs with indistinguishable 404s, require idempotency and reasons for mutations, and keep high-risk flags off. The browser receives no VICIdial, Odoo, n8n, recording, Qwen or database credential.

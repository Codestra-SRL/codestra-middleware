# Lead Automation V1 security boundary

Policy defaults deny. All mutation and delivery switches default false. Event attributes are selected from registered PII-free business-unit schemas. n8n cannot access Odoo or PostgreSQL directly. Middleware revalidates results before an HMAC-authenticated Odoo call. Logs contain opaque identifiers and policy metadata only.

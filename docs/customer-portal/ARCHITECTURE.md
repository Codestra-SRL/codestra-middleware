# Codestra Customer Portal architecture

The portal is a separate customer-facing surface. Browser traffic terminates at the portal frontend and calls only the middleware customer API on 65.109.65.169. Odoo, VICIdial, n8n, Qwen, Qdrant and storage are accessed only through authorized middleware adapters. Customer accounts are tenant/workspace scoped and never inherit internal administrator roles.

Production is disabled by default. Staging uses synthetic tenants and protected, short-lived access references.

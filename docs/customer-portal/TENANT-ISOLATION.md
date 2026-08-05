# Tenant isolation

Every customer query requires a customer tenant scope and role. Middleware queries must constrain tenant and workspace identifiers before loading records. Cross-tenant access is denied and audited. Customer APIs never expose internal audit, security events, prompts or credentials.

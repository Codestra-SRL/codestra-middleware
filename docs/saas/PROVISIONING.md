# Provisioning

Provisioning is asynchronous and idempotent. Requests use a unique idempotency key and progress through validation, account/workspace/Odoo creation, invitation, entitlements, branding and integration placeholders. Failures retry or roll back without duplicate tenants, workspaces or partners.

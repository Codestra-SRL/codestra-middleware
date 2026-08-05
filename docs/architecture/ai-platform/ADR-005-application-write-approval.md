# ADR-005: Application-write approval

## Context
Lead imports and other external writes have material business impact.

## Decision
Application writes require independent feature flags and, where policy requires, an explicit approval record. This foundation keeps Odoo, VICIdial, and Postly writes disabled.

## Alternatives considered
Automatic import after scoring was rejected.

## Security and reliability
Approval is tenant-scoped, role-checked, expiring, and audited.

## Operations and rollback
Kill switches prevent new writes; pending approvals remain reviewable.

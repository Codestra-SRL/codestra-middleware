# ADR-001: AI platform authority boundaries

## Context
AI providers and workflow runners are not durable business systems.

## Decision
Codestra Middleware owns authentication, tenant scope, AI-job state, approvals, retries, audit, and canonical events. n8n orchestrates; Qwen produces structured suggestions; Odoo, VICIdial, and Postly remain authoritative for their domains.

## Alternatives considered
Direct n8n/provider writes were rejected because they bypass policy and audit.

## Security and reliability
All delivery is authenticated, at-least-once, idempotent, and fail-closed.

## Operations and rollback
Disable AI feature flags and stop outbox delivery; persisted jobs remain available for reconciliation.

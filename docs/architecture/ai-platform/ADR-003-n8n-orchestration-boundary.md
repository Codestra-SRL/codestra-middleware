# ADR-003: n8n orchestration boundary

## Context
n8n is useful for routing and transformations but is not a durable system of record.

## Decision
Middleware persists jobs and outbox events before n8n delivery. n8n may call approved gateways and must return a signed, schema-validated result.

## Alternatives considered
Direct n8n database access was rejected.

## Security and reliability
Service authentication, nonce replay protection, tenant matching, and workflow allowlists are mandatory.

## Operations and rollback
Disable routing keys or n8n delivery while preserving queued jobs.

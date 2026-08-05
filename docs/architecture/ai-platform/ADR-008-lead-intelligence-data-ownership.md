# ADR-008: Lead intelligence data ownership

## Context
AI can discover and score leads but cannot establish unsupported ownership claims.

## Decision
Middleware stores source history, collection date, evidence, confidence, and duplicate status. Odoo remains authoritative only after an approved import.

## Alternatives considered
AI-only merging or ownership assertions were rejected.

## Security and reliability
Source data is retained with tenant scope; ambiguous records require review.

## Operations and rollback
Imports remain disabled in this mission; approved records can be reconciled after Odoo recovery.

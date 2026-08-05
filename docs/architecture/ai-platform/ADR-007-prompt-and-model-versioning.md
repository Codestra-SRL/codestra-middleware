# ADR-007: Prompt and model versioning

## Context
Reproducibility requires knowing which prompt and model produced a result.

## Decision
Prompts, prompt versions, models, policies, and output schemas are registry records. Activated prompt versions are immutable; changes create new versions.

## Alternatives considered
Environment-only prompt strings were rejected because they cannot be audited or rolled back.

## Security and reliability
Registries store references, not credentials; disabled placeholders are safe defaults.

## Operations and rollback
Deactivate a version or policy and route new jobs to an approved fallback.

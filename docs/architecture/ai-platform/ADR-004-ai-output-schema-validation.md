# ADR-004: AI output schema validation

## Context
Free-form model output cannot safely drive business workflows.

## Decision
Every result declares a registered schema code/version and is validated before state changes or application commands.

## Alternatives considered
Best-effort parsing was rejected because malformed output could cause unsafe writes.

## Security and reliability
Unknown schemas, oversized payloads, invalid enums, and out-of-range confidence values fail closed.

## Operations and rollback
Schema versions are additive; a bad schema is disabled without rewriting accepted history.

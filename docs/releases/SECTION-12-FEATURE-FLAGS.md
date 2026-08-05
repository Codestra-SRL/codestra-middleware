# Feature-flag validation

Release management, staging, and rollback controls must be enabled for a
certification snapshot. Production activation, automatic deployment, automatic
rollback, unrestricted production, and data deletion flags must be false.

Flag changes are versioned, scoped, approved, audited, and reversible. A flag
snapshot is attached to the release evidence. No AI employee or workflow may
write production flags autonomously.

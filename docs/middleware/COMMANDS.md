# Commands

All writes enter the command bus. Commands are validated, authorized, audited,
idempotent, queued, and reconciled. `core_mutations_enabled` is false by
default; no adapter is called by the control-plane endpoint.

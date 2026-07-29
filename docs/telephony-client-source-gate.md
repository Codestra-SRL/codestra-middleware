# Registry-backed telephony client source gate

Mission: `CODESTRA-MIDDLEWARE-TELEPHONY-CLIENT-V1`

This change is source-only. It does not authorize deployment, adapter
activation, telephony writes, call origination, or production activation.

## Dependency provenance

- Middleware base: `origin/main` at
  `4baccd487b20cdb62fcaa04259a8e32d260c0c32`
- Endpoint Registry and Common Service Client: merged in middleware history
  through `7f10e4d`
- Normalized Odoo delivery client: merged in middleware history through
  `d2bbc0d`
- Odoo dependency: `Codestra-SRL/codestra-odoo-addons` PR #9
- Odoo reviewed head: `c1c7541a4a7daec0b6f5cb70494bc478aa8258c9`
- Odoo merge commit: `7a0b698669bb50c1523da5cd7d531822a1a973b1`

The Odoo commit is a contract dependency and is not the middleware Git base.

## Model inventory

The implementation reuses the existing command, operation, terminal-result,
reconciliation, policy-decision, target-attestation, audit, delivery,
idempotency, dead-letter, allocation, and provisioning-saga models.

One append-only `telephony_operation_transition` model is required because a
mutable current-state column cannot retain independent transition sequence,
hash, idempotency, adapter identity, correlation evidence, or ordering.
No parallel command, result, delivery, policy, audit, or reconciliation journal
was introduced.

## Fail-closed boundaries

- All Odoo and adapter routes resolve through the Endpoint Registry and Common
  Service Client.
- No source contains a telephony host, URL, database address, AMI address,
  extension, context, or trunk.
- Adapter endpoint examples remain disabled and kill-switched.
- Target attestation is mandatory before a mutation or validated Odoo callback.
- A post-transmission timeout becomes an ambiguous durable operation and moves
  to readback. It is never blindly resubmitted.
- Middleware reaches `RECONCILED` only after terminal-result binding, Odoo
  callback, result/projection/mapping/trace readback, and zero material drift.

# HMAC-V2 staging secret delivery

Generate a new random value only during the authorized deployment phase. Store
it in a root-owned staging-only secret directory with mode `0700`; individual
files use mode `0400`. Compose mounts files read-only under `/run/secrets`.

The callback identity and scope are `codestra-n8n-lead-automation` and
`lead-automation.results.write`. Odoo apply uses identity `codestra-middleware`
and scope `lead-automation.odoo-apply.write`. The current authoritative source
uses one Middleware setting for callback verification and Odoo apply signing,
so the same staged value must be delivered to the three isolated participants.
It must not be reused by any unrelated capability.

Rotation creates a new staged value, records a fingerprint only, distributes
it while all feature flags remain false, restarts isolated containers one at a
time, runs signature tests, and revokes the previous value. If verification
fails, restore the prior secret files from the encrypted staging backup and
keep every feature disabled. Logs must redact values and retain only version,
identity, scope, timestamp, and a non-reversible fingerprint.


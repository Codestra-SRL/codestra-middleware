# VICIdial command and event contract map

## Command path

```text
Codestra UI/Odoo
  -> authenticated Command API
  -> telephony_command_journal
  -> policy decision revalidation
  -> endpoint registry resolution and target attestation
  -> middleware telephony client
  -> private VICIdial adapter (disabled by default)
```

The command envelope carries a schema version, public aggregate identifiers,
idempotency key, correlation/causation IDs, policy decision hash, and an
allocation reservation. It intentionally rejects telephone numbers, database
hosts, arbitrary URLs, trunk names, and physical extensions. The dispatcher
persists an operation journal before readback and treats timeouts as ambiguous,
not as permission to issue a second write.

## Event path

```text
VICIdial event collector
  -> signed POST /api/v1/events/vicidial
  -> nonce + timestamp + HMAC validation
  -> schema registry
  -> event_inbox / IntegrationEvent
  -> lifecycle transition and audit
  -> durable Odoo/n8n delivery rows
```

The event endpoint acknowledges only after PostgreSQL commit. Duplicate
idempotency keys replay the original receipt; a changed payload with the same
key is rejected. Call lifecycle transitions are monotonic, and late events do
not move terminal state backwards.

## Operational controls

* `telephony_command_worker_enabled=false`
* `vicidial_provisioning_enabled=false`
* `vicidial_write_enabled=false`
* `live_writes_enabled=false`
* `enable_external_delivery=false`
* `production_n8n_enabled=false`

`Settings.validate_safety()` rejects unsafe combinations at process startup.
No production call or customer-facing write is required for the synthetic
validation path.

## Activation prerequisites

Authenticated execution requires a registered private adapter endpoint, owner-
provided least-privilege credentials, target attestation material, and an
approved staging fixture. These are infrastructure/credential inputs, not
values to be placed in source control or chat.

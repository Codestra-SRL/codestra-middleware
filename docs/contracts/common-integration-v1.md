# Common Integration Contracts v1

`codestra.command.v1` is the only new state-changing command envelope introduced
by this change. `codestra.event.v1` is the normalized cross-service event
envelope. Existing schema-1 VICIdial and publisher-v2 contracts remain strict,
versioned edge contracts and are not silently reinterpreted.

The common contracts:

- reject unknown fields;
- require immutable UUID command/event and correlation identities;
- bind organization, business unit and campaign;
- bind environment and policy hash;
- require canonical payload SHA-256 verification;
- carry explicit PII classification;
- enumerate every initially supported command type;
- reject unknown command types.
- reject duplicate JSON object keys when parsed through the required raw parsers;
- restrict canonical payloads to NFC strings, signed 64-bit integers, booleans,
  null, arrays and string-keyed objects;
- reject floating-point values and bound payload depth, node count and bytes;
- deep-freeze validated payloads;
- require independent approval identity for production commands;
- limit command validity windows to 15 minutes.
- reject raw secret-bearing payload field names.

This change defines contracts only. It creates no route, database table,
worker, mutation, feature activation or compatibility fallback.

Compatibility adapters must be explicit and versioned. A producer cannot select
an arbitrary legacy parser, and a consumer must never guess a contract from
payload contents.

The common envelope is a transport contract, not authorization. Every consumer
must use a reviewed exact command/event registry with a closed payload model,
derive identity and policy authorization from trusted state, and reject any
unregistered type before side effects. Transport authentication must cover the
complete envelope; `payload_hash` is payload-integrity evidence and is not a
substitute for HMAC or a service JWT.

The durable idempotency uniqueness scope is:

`environment + organization_id + campaign_id + command_type + idempotency_key`.

Consumers must derive this scope from validated fields and enforce it in
PostgreSQL. The command-journal milestone will add the corresponding database
constraint and optimistic transition version.

Ingress implementations must use `parse_common_command` or
`parse_common_event`; calling a generic JSON parser would forfeit duplicate-key
rejection. Consumers must also enforce trusted-current-time expiry and clock
skew at authorization and again immediately before dispatch.

`RETRY_SCHEDULED` is reserved for the later bounded-retry profile. It is
intentionally unreachable in the default v1 state transition map. Replay
approval returns a command to `VALIDATING`, never directly to reservation or
dispatch.

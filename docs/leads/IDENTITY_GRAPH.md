# Identity graph

Codestra UUIDs identify people and companies; email, telephone, social, and external-system identifiers are aliases, never primary keys. Every query is tenant-scoped. Deterministic keys may auto-link only at `EXACT`; composite `HIGH`, `MEDIUM`, and `LOW` results enter review. Conflicting strong keys never collapse automatically.

Contact points retain a SHA-256 lookup value and masked display value. The current foundation deliberately does not persist plaintext contact values. Social uniqueness is `(tenant, provider, network, provider_profile_id)`. External references are hashed and represented through safe opaque references.

Merge marks the source `MERGED` and sets `merged_into_id`; it does not delete it. Unmerge clears that pointer and appends a reversal decision. Source identifiers, resolution attempts, attribution evidence, and audit history remain intact.

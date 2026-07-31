# Recording contract alignment decision required

PR A head `817299f2648be9b8c7c29ffd51645bf2e3a5a095` is vendored
byte-for-byte and verified by SHA-256.

Two requirements in the phase instruction cannot both be satisfied:

1. The canonical `recording-event-v1.json` requires a nested `recording` object
   conforming to the full recording contract.
2. The requested n8n event is a flat allowlist and requires
   `object_version_id`, which the canonical event schema neither declares nor
   permits because `additionalProperties` is false.

The canonical reservation and status schemas also establish details that must
remain authoritative:

- reservation requests use nested `recording` metadata;
- status uses the seven states declared by PR A.

This branch does not reinterpret those schemas. The n8n workflow stays inactive
and no publisher is activated. PR A must be amended or an explicitly versioned
n8n projection schema must be approved before the cross-repository n8n event
gate can pass.

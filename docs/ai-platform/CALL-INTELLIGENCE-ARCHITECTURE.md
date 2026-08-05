# Call Intelligence architecture

VICIdial remains authoritative for call and recording metadata. Middleware
creates one idempotent job per tenant and VICIdial unique ID, stores only
protected recording references, validates transcript/analysis schemas, and
controls Odoo updates. n8n is orchestration only; AI services cannot write to
Odoo or VICIdial directly.

The default recording policy is `CALL_RECORDING_PROCESSING_DISABLED`. Real
recordings require lawful notice/consent, retention and access-policy approval.

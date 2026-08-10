# Synthetic lead canary

The canonical fixture uses the reserved address `synthetic-lead@example.invalid`, reserved test telephone `+15555550100`, a synthetic Postly/Facebook profile reference, and the message classification `QUOTE_REQUEST`. The raw message is not persisted in the test ledger.

Ten resolutions with identical deterministic keys must create one `PersonIdentity`. Ten campaign-scoped lead upserts must create one `LeadRecord`. Ten deliveries of the same source event create one interaction; a second synthetic website-form event attaches a second interaction to the same person and lead.

The expected positive-policy result uses `consent=UNKNOWN`, so the safe result is `MANUAL_REVIEW`, not an outbound call or email. The score is explainable through bounded component values rather than an opaque AI-only value.

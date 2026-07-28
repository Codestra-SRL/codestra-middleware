# Lifecycle coherence policy

Correlation uses normalized LinkedID, with UniqueID fallback only when LinkedID
is absent. Local channel suffixes are collapsed. STARTED may transition to
CONNECTED or ENDED; ENDED without CONNECTED represents no-answer, busy,
abandoned, or failed completion. ENDED is terminal and cannot regress.

Duplicate event IDs are idempotent. Duplicate semantic transitions with a new
event ID are recorded without applying a second state transition. Out-of-order
events, ambiguous multiple-LinkedID transfers, unapproved transfers, orphan
CONNECTED/ENDED events, restart gaps, and unknown boot sessions are
quarantined. Incomplete calls are bounded by an approved timeout and resolved
to an explicit incomplete disposition; the timeout remains
`BUSINESS_APPROVAL_REQUIRED`.

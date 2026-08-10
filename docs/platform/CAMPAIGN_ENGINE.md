# Campaign engine

The durable state machine is `DRAFT -> CONTENT_GENERATING -> CONTENT_REVIEW -> APPROVAL_REQUIRED -> APPROVED -> SCHEDULED -> ACTIVE`, with explicit pause, completion, failure and cancellation branches. Illegal transitions return `SOCIAL_CAMPAIGN_TRANSITION_INVALID` with HTTP 409.

Every transition records actor, old/new state, reason, correlation and optional AI/approval references. Content is versioned by campaign/network/language; approval belongs to one exact version and blocked-risk content cannot be approved.

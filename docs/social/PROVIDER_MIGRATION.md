# Provider migration

Canary routing applies only to new commands whose complete Codestra account set appears in `HOOTSUITE_CANARY_ACCOUNT_IDS`. A persisted post or job always resolves its recorded provider. Mixed or non-allowlisted account sets remain on the configured default.

There is no automatic dual publishing or cross-provider failover. Rollback changes routing for new operations only; it never rewrites provider IDs, historical ownership, or scheduled jobs.

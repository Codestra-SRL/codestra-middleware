# Phase 3 rollback

1. Set `SOCIAL_PROVIDER_MIGRATION_MODE=disabled` and `HOOTSUITE_ENABLED=false`.
2. Keep `SOCIAL_PUBLISH_ENABLED=false` and the default provider unchanged.
3. Preserve all Hootsuite-owned posts, jobs, account mappings, provider IDs, events, and audit evidence.
4. Revoke the staging OAuth grant and remove only its runtime token file if one was created.
5. Revert the Phase 3 source commit/image in staging.
6. Verify Postly-owned jobs still resolve to Postly and no Odoo write gate changed.

No runtime activation occurred in this phase, so source rollback requires no production data or network mutation.

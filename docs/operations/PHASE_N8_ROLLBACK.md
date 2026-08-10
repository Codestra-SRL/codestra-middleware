# Phase N8 rollback

Phase N8 runs only in disposable infrastructure. Rollback is:

1. Set `IDENTITY_GRAPH_ENABLED=false`.
2. Set `LEAD_INTELLIGENCE_ENABLED=false`.
3. Set `NEXT_BEST_ACTION_ENABLED=false`.
4. Set `ATTRIBUTION_ENGINE_ENABLED=false` and `REVENUE_EVENT_SYNC_ENABLED=false`.
5. Stop the isolated middleware and worker processes.
6. Preserve the synthetic evidence database until acceptance review is complete, then remove it under the test-data retention policy.
7. Restore the prior exact image if an isolated runtime image was changed.

Rollback never deletes production data or rewrites identity, lead, provider, or attribution ownership. Production social publishing, Odoo writes, VICIdial commands, and automatic contacting remain disabled throughout.

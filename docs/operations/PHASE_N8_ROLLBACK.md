# Phase N8 rollback

Phase N8 runs only in disposable infrastructure. Rollback is:

1. Set `IDENTITY_GRAPH_ENABLED=false`.
2. Set `LEAD_INTELLIGENCE_ENABLED=false`.
3. Set `NEXT_BEST_ACTION_ENABLED=false`.
4. Set `ATTRIBUTION_ENGINE_ENABLED=false` and `REVENUE_EVENT_SYNC_ENABLED=false`.
5. Stop the isolated middleware and worker processes.
6. Preserve the synthetic evidence database until acceptance review is complete, then remove it under the test-data retention policy.
7. Restore the prior exact image if an isolated runtime image was changed.

For the isolated n8n promotion, unpublish the `CdstPhaseN8BusinessCanaryV1` workflow and stop the disposable n8n, API, and PostgreSQL containers. Remove only volumes whose names were recorded as Phase N8 disposable resources. Confirm the pre-existing middleware and n8n containers retain their prior image digests and health before optionally recreating the isolated stack.

Rollback never deletes production data or rewrites identity, lead, provider, or attribution ownership. Production social publishing, Odoo writes, VICIdial commands, and automatic contacting remain disabled throughout.

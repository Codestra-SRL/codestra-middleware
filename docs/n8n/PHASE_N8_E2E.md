# Phase N8 n8n path

The synthetic event is committed to PostgreSQL before n8n work begins. A unique `(event_id, target)` delivery is leased and mapped once to a governed `N8nRuntimeExecution`. Middleware signs the canonical envelope and posts it to `/webhook/codestra-social-router-v1`. The isolated workflow calls `/api/v1/n8n-runtime/social-authorize`, executes the N7 business APIs with bearer authentication, and HMAC-signs `/api/v1/n8n-runtime/results`. Reconciliation must then mark the delivery delivered.

An expired lease is changed to `retry_wait`, proving worker-crash recovery without losing the canonical event. Existing n8n authentication, replay, callback, outage, and idempotency suites remain part of the repository-wide gate.

Render the source-controlled workflow with:

```shell
python scripts/render_phase_n8_n8n_workflow.py --output /protected/path/workflow.json
```

Import it inactive, then publish it only in a network-isolated n8n staging instance. Permit only the `crypto`, `http`, and `url` Node built-ins. Supply middleware and HMAC credentials through protected runtime configuration, never in the workflow JSON. Do not connect the instance to production Postly, Odoo, or VICIdial.

Run `scripts/run_phase_n8_http_canary.py` from the same isolated network. Certification requires `COMPLETED`, a delivered integration delivery, all five attribution IDs, a complete immutable correlation trace, and `external_actions=0`.

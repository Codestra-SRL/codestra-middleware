# Codestra Postly offline acceptance evidence

This evidence covers only the middleware-owned, deterministic mock boundary.
It does not claim authenticated Postiz runtime access or a live social post.

## Executed checks

* `npm test` in `postly-integration`: 8 tests passed.
* Python 3.12 container targeted suite: 7 tests passed, 1 test skipped because
  no disposable PostgreSQL URL was provisioned.
* Mock lifecycle covers Odoo request, n8n proposal, human approval, idempotent
  scheduling, temporary failure retry, uncertain-write reconciliation, signed
  callback validation, and analytics readback.
* Reconciliation is bound to the organization, workspace, content job, and
  idempotency claim; a result from another workspace cannot satisfy an
  uncertain write.
* No provider network call, OAuth flow, live social account write, or public
  publication was performed.

## Safe defaults

```text
SOCIAL_ACCOUNT_CONNECTION_ENABLED=false
SOCIAL_SCHEDULING_ENABLED=false
SOCIAL_LIVE_PUBLISHING_ENABLED=false
SOCIAL_PUBLISH_NOW_ENABLED=false
PRODUCTION_ACTIVATION_ENABLED=false
REMOTE_LIVE_POST_COUNT=0
LIVE_SOCIAL_ACCOUNT_WRITE_COUNT=0
```

## Remaining external prerequisites

Authenticated validation requires owner-provided access to the external Postiz
deployment/source, a least-privilege organization credential or staging test
workspace, and approved OAuth test account access. Those values must be
entered on the server-side secret manager and must never be placed in source,
workflow exports, evidence, or chat.

# Phase 2 acceptance

## Passed locally

- Phase 1 exact-SHA CI and provider-neutral baseline;
- durable SQL intent/idempotency/job/audit/outbox transaction;
- database failure before commit produces zero provider calls and zero signal rows;
- atomic job leasing, single provider dispatch, attempt persistence, and IntegrationEvent creation;
- persistent webhook deduplication and normalized event persistence;
- unknown Postly read-timeout fail-closed classification;
- minimal Redis signal contract;
- migration upgrade/downgrade/re-upgrade on disposable PostgreSQL.

## External blockers

The Postly peer is reachable at `10.40.0.3` over the private VLAN and its HTTPS listener responds, but the deployed Postiz runtime has no dedicated staging machine credential, no staging-safe account, and no signed outbound webhook contract. Consequently authenticated account discovery, real draft/schedule/cancel, webhook round-trip, n8n staging delivery, and controlled provider tests are not certified. Publishing remains blocked.

This phase must not be reported as fully certified until the peer credential and signed-webhook blockers are resolved and required exact-SHA CI for the Phase 2 PR passes.

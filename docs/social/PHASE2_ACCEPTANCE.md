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

Private peer `10.40.0.2` is unreachable, SSH to `49.12.145.107` is unauthorized, and no approved local Postly secret was found. Consequently Postly runtime/API/auth/account discovery, real draft/schedule/cancel, webhook round-trip, n8n staging delivery, and controlled load/stability tests are not certified. No staging-safe account was identified, so publishing remains blocked.

This phase must not be reported as fully certified until remote access and required exact-SHA CI for the Phase 2 PR pass.

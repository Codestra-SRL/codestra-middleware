# Codestra Middleware ↔ Postly adapter contract v1

Middleware is the authorization, approval, idempotency, audit, retry, and reconciliation authority. Postly receives a write only after an immutable approval record exists. n8n can propose content but cannot invoke Postly.

Lifecycle: `draft → generating → pending_review → approved → queued → media_uploaded → scheduled → publishing → published`. Adapter results use the normalized states defined in `schemas/postly-result.schema.json`.

Every command must validate `schemas/postly-command.schema.json`. The adapter rejects absent approval metadata, organization/workspace mapping mismatches, past schedules, and integration IDs outside the mapped Postly organization. Social OAuth tokens and customer secrets never enter a command.

Operations map to the installed endpoints documented in `POSTLY_API_ENDPOINT_INVENTORY.md`. `get_post` is implemented as a bounded date-range lookup because this release lacks a public single-post read. Deletion is allowed only before a terminal publish state and must be audited.

## Duplicate protection

Postiz v2.22.1 has no native idempotency. Middleware must atomically claim:

`organization_id + content_job_id + content_version + integration_id + scheduled_at`

before upload/scheduling. A repeat returns the stored result. Uncertain timeouts become `unknown_requires_reconciliation`; never blindly retry a schedule call. Reconcile first by bounded date range and stored Postly group/post identifiers.

## Errors and retries

Normalize into authentication, authorization, validation, rate_limit, temporary, permanent_provider, conflict, not_found, timeout, or unknown. Retry only rate limits, temporary failures, and timeouts that reconciliation proves did not create a post. Use capped exponential backoff with jitter. Partial provider results are terminal for successful integrations and separately recoverable for failed ones only after human policy approval.

## Callback decision

Native webhooks do not meet authentication/replay requirements. Initial production mode is polling: 30 seconds for near-due publishing, then 2/5/15 minute bounded backoff, stop at terminal states, alert after the campaign deadline. A future adapter callback to `POST https://api.codestra.agency/api/v1/social/provider-events` must use HMAC-SHA256 over `timestamp.rawBody`, a unique callback ID, five-minute skew, replay storage, TLS, source allowlisting, and private routing.

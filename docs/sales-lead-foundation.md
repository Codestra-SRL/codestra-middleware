# Sales lead intake and verification foundation

## Contracts and endpoints

The strict request schema is `codestra.sales.lead-candidate.v1`; unknown fields and arbitrary nested metadata are rejected. Tenant and campaign are mandatory. Evidence is limited to 25 entries and 1,000 characters per snippet. Requests are limited to 128 KiB (or the lower global limit). Timestamps must be UTC. Evidence URLs allow only HTTP(S), reject credentials, executable downloads, localhost/internal suffixes, and non-global literal IP addresses. Raw HTML is rejected.

The response schema is `codestra.sales.lead-resolution.v1`, is always `dry_run: true`, and returns deterministic scores, stable reason codes, gate states, correlation ID, and policy version. Decisions are `NET_NEW`, `EXACT_EXISTING`, `POSSIBLE_DUPLICATE`, `BLOCKED`, `REJECTED`, and `CONFLICT`.

Endpoints:

- `POST /api/v1/sales/lead-candidates/validate`
- `POST /api/v1/sales/lead-candidates/resolve` (`Idempotency-Key` required)
- `POST /api/v1/sales/verification-jobs` (`Idempotency-Key` required)
- `GET /api/v1/sales/verification-jobs/{job_id}` (`X-Tenant-ID` required)
- `GET /api/v1/sales/verification-jobs/{job_id}/results` (`X-Tenant-ID` required)
- `POST /api/v1/sales/scraper-results` (HMAC-authenticated)

All API errors use `{error: {code, message, correlation_id, retryable}}`. Stable codes include `LEAD_CANDIDATE_INVALID`, `REQUEST_TOO_LARGE`, `SALES_FEATURE_DISABLED`, `IDEMPOTENCY_PAYLOAD_CONFLICT`, `DRY_RUN_JOB_INVALID`, `JOB_NOT_FOUND`, `INVALID_CONTENT_TYPE`, `SCRAPER_INGEST_DISABLED`, `MISSING_SIGNATURE`, `INVALID_SIGNATURE`, `EXPIRED_TIMESTAMP`, `REPLAYED_NONCE`, `MODIFIED_PAYLOAD`, `WRONG_TENANT_BINDING`, and `UNKNOWN_SCRAPER_IDENTITY`.

## Normalization and identity

Original values remain in the candidate/evidence. Comparison strings use Unicode NFKC, case folding, whitespace/punctuation normalization, and common legal-suffix removal. Domains remove scheme/path/query/fragment/leading `www` and use IDNA. Registrable-domain collapsing is deliberately not performed without a maintained public-suffix dataset, avoiding incorrect country-domain collapse. Telephone normalization uses `phonenumbers` and produces E.164 only with sufficient country context; extensions remain separate. Ambiguous numbers are rejected. Email domain casing is normalized, while local-part evidence is preserved.

Company and contact matching remain separate. Registration plus jurisdiction scores 100; exact domain 95; strong name/location 85; name alone 70/review. Exact non-role business email scores 100; E.164 plus confirmed company 95; exact name plus a corroborated company scores 80/review. Defaults are exact >=90 and review 70-89, policy `sales-lead-v1.0`. Role email, switchboard, fuzzy person/company name, city, or AI output never auto-merge.

Possible duplicates persist tenant/campaign, candidate, Odoo reference candidates, scores, reason codes, evidence hashes, policy version, timestamps, state, and eventual reviewer fields. Phase 1 never modifies Odoo.

## Compliance, Odoo, providers, and jobs

Gate precedence is global DNC, internal global suppression, campaign DNC, withdrawn consent, then unknown-consent review. Scores, AI, and provider data cannot override a block. Authoritative dependency failure returns `DEPENDENCY_UNAVAILABLE` and fails closed. Source consent claims are evidence only.

The Odoo port exposes bounded tenant-filtered reads (maximum 100) and no create/update/delete methods. The fake guard certifies all write counts remain zero. Paid provider adapters (Hunter, Apollo, Twilio Lookup, OpenCorporates, OpenAI) are disabled, bounded by timeout/retry/rate/circuit/cost metadata, and return `DEPENDENCY_UNAVAILABLE` rather than invented data. OpenAI classification is never an input to identity or compliance.

Verification jobs enforce `source=odoo`, `dry_run=true`, `write_changes=false`, `publish_to_vicidial=false`, and batch size 1-100. States are `QUEUED`, `RUNNING`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `FAILED`, and `CANCELED`. Classifications are `VERIFIED_VALID`, `VERIFIED_PARTIAL`, `INVALID_EMAIL`, `INVALID_PHONE`, `DOMAIN_INACTIVE`, `COMPANY_INACTIVE`, `EXACT_DUPLICATE`, `POSSIBLE_DUPLICATE`, `DNC_BLOCKED`, `SUPPRESSED`, `CONSENT_WITHDRAWN`, `STALE`, `NEEDS_REVIEW`, and `DEPENDENCY_UNAVAILABLE`.

## Idempotency, webhook authentication, and audit

Canonical JSON SHA-256 binds `(tenant_id, operation, idempotency_key)`. Same key/payload returns the original result; changed payload returns HTTP 409; locking commits a concurrent key once; tenant scopes do not leak. Database records store protected key/payload hashes, reference, state, correlation, and expiry—not raw PII or credentials.

Scraper HMAC-V1 binds signature version, scraper identity, tenant, campaign, request ID, UTC timestamp, nonce, and body SHA-256. Timestamp TTL is five minutes. Nonces are replay-protected. Content type, size, body integrity, identity, and payload/header tenant/campaign/request bindings are enforced. There is no development bypass and examples intentionally omit secrets.

Append-only audit events support candidate received/validated/rejected, resolution, duplicate review, gates, jobs, provider calls, webhook acceptance/rejection, replay, and idempotency conflict. Events contain protected hashes and bounded identifiers, never credentials or unnecessary personal data.

## Feature flags and rollback

All flags default false: `SALES_LEAD_INTAKE_ENABLED`, `SALES_IDENTITY_RESOLUTION_ENABLED`, `SALES_ODOO_READ_ONLY_LOOKUP_ENABLED`, `SALES_VERIFICATION_JOBS_ENABLED`, `SCRAPER_RESULT_INGEST_ENABLED`, `HUNTER_PROVIDER_ENABLED`, `APOLLO_PROVIDER_ENABLED`, `TWILIO_LOOKUP_PROVIDER_ENABLED`, `OPENCORPORATES_PROVIDER_ENABLED`, `OPENAI_LEAD_CLASSIFICATION_ENABLED`, `ODOO_WRITE_ENABLED`, `VICIDIAL_PUBLICATION_ENABLED`, and `OUTREACH_ENABLED`.

Rollback: keep every flag false, stop any Phase 1 worker, then downgrade from `0033_sales_lead_foundation` to `0032_ai_worker_queue_runtime`. The downgrade removes only new empty Phase 1 tables; no production data rewrite is part of the upgrade.

## Phase 2 Server C handoff

The self-hosted scraper at `49.12.145.107` must send canonical JSON matching `codestra.sales.lead-candidate.v1` to Server A `/api/v1/sales/scraper-results`, never Odoo/n8n/VICIdial. It must supply `Content-Type: application/json`, `X-Scraper-Identity`, `X-Tenant-ID`, `X-Campaign-ID`, `X-Request-ID`, `X-Codestra-Timestamp`, unique `X-Codestra-Nonce`, `X-Content-SHA256`, `X-Signature-Version: HMAC-V1`, and `X-Codestra-Signature`. Header tenant/campaign/request values must equal the payload. It must retain bounded public evidence, retry with a new nonce, reuse the same intake idempotency identity for the same logical payload, and treat every result as dry-run until a later governance approval.

Known Phase 1 limitations: the application repository is currently an in-process reference implementation behind ports; production persistence and job execution wiring remain disabled, provider calls are fakes, hostname DNS resolution is not performed during schema validation, and registrable-domain extraction awaits an approved public-suffix dependency.

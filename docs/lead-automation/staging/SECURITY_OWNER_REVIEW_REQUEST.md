# Security-owner review request for PR #68

This is a review request, not an approval or a deployment authorization. The
review target is the exact live PR head reported by GitHub after this document
is committed. A signed decision must repeat that 40-character SHA and is
invalid after any subsequent commit.

## Requested authorization boundary

The only approvable scope is `server_a_isolated_staging`. Approval does not
authorize production deployment, production activation, customer data, real
calling, email or SMS delivery, social posting, external lead distribution,
unrestricted n8n activation, Server B access, or recording deletion.

The source decision must retain:

```text
production_deployment_gate=blocked
production_activation_gate=blocked
server_b_access_gate=blocked
customer_data_gate=blocked
```

## Technical controls and evidence

- All feature flags and communication paths are default-off.
- Deployment and operations services require explicit Compose profiles.
- CI executes `docker compose up --no-start` on the default path and proves no
  deployment- or operations-profile service was created.
- The Compose network is internal and the manifest publishes zero host ports.
- File-backed secrets are granted per service. Host preflight requires a
  root-owned `0700` directory, root-owned regular `0400` files, no symlinks or
  hard links, and resolved-path containment. It does not rely on ignored
  Compose `uid`, `gid`, or `mode` attributes.
- n8n runs with a read-only root filesystem, bounded tmpfs mounts for `/tmp`
  and `/home/node/.cache`, and a dedicated staging-only volume for
  `/home/node/.n8n`. CI proves restart persistence of the encryption identity
  while workflow activation and bindings remain zero.
- Every image reference is digest-pinned. Local CycloneDX SBOM checksums,
  compression, parsing, and image subjects are validated.
- Cosign verification is fail-closed for Codestra images and restricts the
  certificate identity and GitHub Actions OIDC issuer. Missing third-party
  signatures are reported as unavailable, not represented as verified.
- Middleware database and migration tests, rollback restoration, application
  startup, disabled defaults, static validation, schemas, and Python tests run
  in exact-SHA CI.
- Odoo source is pinned to authoritative main commit
  `f3a51feff8b06021bead395add82a5c5aed45ee5`, including the merged PR #16
  multi-company isolation repair. Its checksummed isolation evidence is
  `9bb326f97c5f89dc6dd75f6789a6fdd9815d3d7101c4bea3449316b533b63003`.
- Middleware source is pinned to authoritative main commit
  `f48761d35f1c88b3a9960484cc7252f10644916b`, including the merged PR #73
  caller-scope repair. Its merged-main evidence is recorded under
  `deploy/lead-automation-staging/security/isolation/`.

## Exact image subjects

```text
docker.io/codestra/lead-staging-middleware@sha256:c0f4f753d589f473e2cbd1054ae7602eea60a3120585a05d55729f494fe8dd6f
docker.io/n8nio/n8n@sha256:e4804b13ae6e2064fa30e5bbfc14b86d0a52eb8a3aa2c351a227314ac90ff666
docker.io/library/odoo@sha256:e415f9924395e7521245813135112f264b9222bcde3b1d3c2ee9ff073081540a
docker.io/library/postgres@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193
docker.io/library/redis@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2
```

The allowed signed-decision identity is
`https://github.com/Codestra-SRL/codestra-middleware/.github/workflows/security-owner-decision-sign.yml@refs/heads/main`
with issuer `https://token.actions.githubusercontent.com`. The detached
Sigstore bundle must verify against the immutable decision record. An unsigned
boolean or an ordinary PR approval is insufficient.

## Vulnerability evidence and residual risks

Machine-bound counts are in
`deploy/lead-automation-staging/security/vulnerability-counts.json`. Current
candidate evidence includes findings requiring an explicit, digest-bound,
time-limited security decision: PostgreSQL has 1 Trivy Critical, 14 Trivy High,
and 44 Grype High-or-Critical; n8n has 8 Trivy High and 14 Grype
High-or-Critical; Middleware has 10 Grype High-or-Critical. These findings
cannot qualify a protected-main production release unless remediated or
covered by an independently signed exception accepted by the release policy.

Additional residual risks are the pending Codestra Middleware image signature
and unavailable upstream signatures or attestations. The allowlisted decision
signing workflow is present on protected main, but no Security Owner decision
has been signed. These conditions keep staging execution and release
publication blocked.

## Required signed decision

The approved document and immutable external record must contain the exact PR
head, exact image digest map, signer identity, authority reference, finite
issuance and expiration timestamps, compensating controls, revocation
conditions, and detached signature bundle. Validation checks the allowlist,
signature, exact SHA, digests, vulnerability counts, expiry, scope, and all
blocked production gates.

## Changed-file inventory

The review covers the following complete inventory, including this request:

```text
.github/workflows/lead-automation-staging-preparation.yml
Dockerfile
app/adapters/odoo/lead_automation.py
app/core/config.py
app/core/lead_automation.py
deploy/lead-automation-staging/README.md
deploy/lead-automation-staging/compose.yaml
deploy/lead-automation-staging/scripts/probe-container-secrets.sh
deploy/lead-automation-staging/scripts/probe-n8n-storage.sh
deploy/lead-automation-staging/scripts/test-default-profile.sh
deploy/lead-automation-staging/scripts/validate-secret-permissions.sh
deploy/lead-automation-staging/scripts/verify-image-signatures.sh
deploy/lead-automation-staging/security/image-security-decision.json
deploy/lead-automation-staging/security/image-security-decision.schema.json
deploy/lead-automation-staging/security/image-verification-policy.json
deploy/lead-automation-staging/security/isolation/MIDDLEWARE-TENANT-ISOLATION-EVIDENCE.txt
deploy/lead-automation-staging/security/isolation/MIDDLEWARE-TENANT-ISOLATION-SHA256.txt
deploy/lead-automation-staging/security/isolation/MIDDLEWARE-TENANT-ISOLATION-TESTS.json
deploy/lead-automation-staging/security/isolation/ODOO-MULTI-COMPANY-ISOLATION-EVIDENCE.txt
deploy/lead-automation-staging/security/sbom/README.md
deploy/lead-automation-staging/security/sbom/SHA256SUMS
deploy/lead-automation-staging/security/sbom/middleware.cdx.json.gz
deploy/lead-automation-staging/security/sbom/n8n.cdx.json.gz
deploy/lead-automation-staging/security/sbom/odoo.cdx.json.gz
deploy/lead-automation-staging/security/sbom/postgres.cdx.json.gz
deploy/lead-automation-staging/security/sbom/redis.cdx.json.gz
deploy/lead-automation-staging/security/scans/middleware-grype-high-critical.json
deploy/lead-automation-staging/security/vulnerability-counts.json
deploy/lead-automation-staging/security_decision.py
deploy/lead-automation-staging/staging.env.example
deploy/lead-automation-staging/synthetic-fixtures.json
deploy/lead-automation-staging/tests/test-secret-permissions.sh
deploy/lead-automation-staging/tests/test_security_decision.py
deploy/lead-automation-staging/validate.py
deploy/lead-automation-staging/verify_supply_chain.py
deploy/n8n/lead-automation/lead-automation-generic-v1.json
deploy/n8n/lead-automation/schemas/lead-automation-result-v1.json
deploy/n8n/lead-automation/schemas/lead-event-v1.json
deploy/n8n/lead-automation/schemas/provenance-manifest-v1.json
deploy/n8n/lead-automation/tests/check_workflow_source.py
deploy/n8n/lead-automation/tests/test_workflow_contract.py
deploy/n8n/lead-automation/tests/workflow_contract.py
deploy/n8n/lead-automation/workflow-manifest-v1.json
docs/lead-automation/staging/ARCHITECTURE.md
docs/lead-automation/staging/BACKUP-RESTORE.md
docs/lead-automation/staging/CONTROLLED-DEPLOYMENT.md
docs/lead-automation/staging/HMAC-V2-SECRETS.md
docs/lead-automation/staging/MIDDLEWARE-MIGRATION.md
docs/lead-automation/staging/N8N.md
docs/lead-automation/staging/OBSERVABILITY.md
docs/lead-automation/staging/ODOO.md
docs/lead-automation/staging/ROLLBACK.md
docs/lead-automation/staging/SECURITY_OWNER_REVIEW_REQUEST.md
docs/security/N8N-STAGING-RISK-ACCEPTANCE.md
docs/security/POSTGRES-STAGING-RISK-ACCEPTANCE.md
docs/security/SECURITY_OWNER_DECISION.md
schemas/lead-automation/SHA256SUMS.json
schemas/lead-automation/lead-automation-result-v1.json
schemas/lead-automation/lead-event-v1.json
schemas/lead-automation/lead-odoo-ack-v1.json
schemas/lead-automation/lead-odoo-apply-v1.json
scripts/check_lead_automation.py
tests/test_lead_automation.py
tests/test_lead_odoo_apply.py
```

The exact inventory must be regenerated from GitHub immediately before review;
any difference invalidates this request and requires a new review.

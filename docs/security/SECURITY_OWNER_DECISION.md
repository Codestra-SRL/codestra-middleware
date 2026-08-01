# Security owner decision required

This document is intentionally **not an approval**. Codex cannot identify or
impersonate the organization's security-risk owner, and ordinary code review
does not constitute risk acceptance.

## Decision targets

- n8n image:
  `n8nio/n8n@sha256:e4804b13ae6e2064fa30e5bbfc14b86d0a52eb8a3aa2c351a227314ac90ff666`
- PostgreSQL image:
  `postgres@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193`
- Middleware candidate image:
  `codestra/lead-staging-middleware@sha256:c0f4f753d589f473e2cbd1054ae7602eea60a3120585a05d55729f494fe8dd6f`
- Exact scanner counts are machine-bound in
  `deploy/lead-automation-staging/security/vulnerability-counts.json`:
  n8n 0 Critical/8 High in Trivy and 14 High-or-Critical in Grype;
  PostgreSQL 1 Critical/14 High in Trivy and 44 High-or-Critical in Grype;
  Middleware 0 Critical/0 High in Trivy and 10 High-or-Critical in Grype.
- Environment: isolated staging only.
- Risk packages: `N8N-STAGING-RISK-ACCEPTANCE.md` and
  `POSTGRES-STAGING-RISK-ACCEPTANCE.md`.
- Maximum expiry: August 30, 2026.
- Production deployment: blocked.
- Production activation: blocked.

## Required security-owner response

An authorized security owner must record an auditable decision containing all
of the following:

```text
SECURITY_OWNER_NAME=
SECURITY_OWNER_ROLE_OR_TEAM=
SECURITY_OWNER_AUTHORITY_EVIDENCE=
DECISION=ACCEPTED|REJECTED
ACCEPTED_IMAGE_DIGEST=sha256:e4804b13ae6e2064fa30e5bbfc14b86d0a52eb8a3aa2c351a227314ac90ff666
ACCEPTED_POSTGRES_IMAGE_DIGEST=sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193
ACCEPTED_MIDDLEWARE_IMAGE_DIGEST=sha256:c0f4f753d589f473e2cbd1054ae7602eea60a3120585a05d55729f494fe8dd6f
ACCEPTED_SCOPE=ISOLATED_STAGING_ONLY
ACCEPTED_FINDING_LIST=N8N-STAGING-RISK-ACCEPTANCE.md,POSTGRES-STAGING-RISK-ACCEPTANCE.md
APPROVAL_TIMESTAMP=
EXPIRY_TIMESTAMP=
APPROVAL_RECORD_URL_OR_SIGNED_REFERENCE=
```

Acceptance is invalid if the digest, finding list, scope, controls, or expiry
does not match exactly; if the approver's authority is not independently
verifiable; or if it is recorded only as an ordinary PR approval.

Risk acceptance cannot substitute for the missing Codestra image-signature
gate. The exact Middleware digest must receive and verify a Codestra-controlled
Cosign signature or supported GitHub attestation before merge.

Until a valid decision exists:

```text
SECURITY_OWNER_ACCEPTANCE_PRESENT=NO
FINAL_STATUS=LEAD_AUTOMATION_SECURITY_OWNER_DECISION_REQUIRED
PRODUCTION_DEPLOYMENT_GATE=BLOCKED
PRODUCTION_ACTIVATION_GATE=BLOCKED
```

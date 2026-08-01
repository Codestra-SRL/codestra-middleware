# Cross-repository inactive-staging import gate

This gate authorizes only an inactive n8n workflow import into Server A isolated
staging. It does not authorize activation, a canary, persistent deployment,
production, Server B, customer data, calls, email, or SMS.

The canonical decision binds, in order, exactly one full SHA for each of:

1. `Codestra-SRL/codestra-middleware`
2. `Codestra-SRL/codestra-odoo-addons`
3. `Codestra-SRL/codestra-n8n-workflows`

Use `scripts/security/verify-cross-repository-review.sh`; do not invoke the
Python policy module as an authorization boundary. The wrapper verifies a
Sigstore bundle against the exact protected-main workflow identity and exact
GitHub Actions issuer before evaluation. The Python evaluator invokes Cosign
itself and accepts no caller-supplied boolean or verification-message claim.

The protected signing workflow must derive repository existence, current PR
heads, exact-head CI, reviewer authentication and authorization, commit authors
and co-authors, package creator, and revocation state from GitHub APIs. Those
facts must not be supplied by a fixture or accepted from an unsigned caller.
Until `.github/workflows/cross-repository-review-sign.yml` exists on protected
`main`, produces the required bundle, and its environment enforces an
independent authorized reviewer, no real decision can pass this gate.

The evaluator emits exactly one canonical JSON object on stdout. The only
successful `final_status` is:

```text
{"final_status":"APPROVED_FOR_INACTIVE_STAGING_IMPORT",...}
```

Every validation failure exits nonzero, sets
`inactive_staging_import_allowed` to `false`, and emits a single structured
result whose status is:

```text
{"final_status":"BLOCKED_GOVERNANCE_EVIDENCE_INVALID",...}
```

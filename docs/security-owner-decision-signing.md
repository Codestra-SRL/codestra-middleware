# Security-owner decision signing

The `security-owner-decision-sign.yml` workflow creates a canonical security decision and signs it with GitHub OIDC and keyless Sigstore. It does not deploy software, modify packages, write repository content, access Server B, or authorize production.

Before merging this workflow, repository administrators must configure the `security-owner-decision-signing` GitHub Environment with authorized Security Owner reviewers and prevent administrator bypass where organization policy permits. The workflow must exist on protected `main` before anyone dispatches it; feature-branch runs are rejected.

Required independent reviews before merge:

- workflow-security and script-injection review;
- confirmation that every third-party action is pinned to an immutable commit SHA;
- `contents: read` and `id-token: write` permission review;
- exact-head CI on this governance PR;
- protected-branch and required-review compliance;
- confirmation that PR #68 was not modified or used to carry this workflow.

The generated decision always leaves production deployment, production activation, Server B access, and customer-data access blocked. A signed decision is evidence of the explicitly supplied security review only; it is not restore authorization, deployment authorization, or activation authorization.

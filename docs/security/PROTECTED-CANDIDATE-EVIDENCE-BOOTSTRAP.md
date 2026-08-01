# Protected candidate-image evidence bootstrap

This bootstrap breaks the trust cycle in which a candidate pull request would
otherwise provide the code used to evaluate itself. The workflow and every
evidence helper execute from protected `main`; only the Docker build context is
checked out from the verified live pull-request head.

The manual workflow requires an exact repository, pull-request number, and
40-character source SHA. It verifies the live open PR and base branch before
building. Package publication uses the protected `security-owner-signing`
environment and the job has only `contents: read`, `pull-requests: read`, and
`packages: write`. No pull-request event receives secrets.

The evidence package contains the immutable image digest, CycloneDX SBOM,
provenance, Trivy and Grype output, a canonical manifest, checksums, and an
unsigned decision request. The request is always pending with acceptance false;
deployment, activation, Server B, and customer-data gates remain blocked. This
workflow performs no signing, deployment, activation, or canary action.

Trust identities are intentionally distinct: `TRUSTED_WORKFLOW_SHA` is the
protected-main revision executing the evaluators, while `TARGET_SOURCE_SHA` is
the verified PR head being built. `CANDIDATE_IMAGE_DIGEST` identifies the
published immutable image. These values must never be conflated.

Artifacts are retained for 30 days. Candidate packages remain staging-only and
are addressed by immutable digest. Rollback is removal of the workflow and
helpers from `main`; already uploaded evidence remains non-authorizing and can
be deleted under repository retention policy. No Security Owner approval or
exception is created by this bootstrap.

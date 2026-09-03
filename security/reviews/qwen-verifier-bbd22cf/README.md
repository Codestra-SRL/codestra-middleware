# Qwen verifier independent Security Owner review

This pull request contains inert, non-secret review evidence only. It does not authorize deployment or signing.

## Exact review subject

- Candidate commit: `bbd22cf7a9ff1dd7d6ef12504d21031bc1f5ab75`
- Image: `ghcr.io/codestra-srl/qwen-auth-verifier@sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef`
- SBOM SHA-256: `380c366db3c70f743a675285cff7665d2ea86523f5967b76d53293a61b1f09ec`
- Normalized OpenAPI SHA-256: `590ceab381e42c71f2eed69a92c096b3f1425f4e927e28d48745a0880eaf67ac`
- Authentication contract SHA-256: `ffab29882b514041c438d7568bec5d8ec8c32c461560d6f4e8e9e32ae89d1b2d`
- Security Owner: Evelin Appolon (`kazan555`, immutable GitHub user ID `77101516`)

## Required independent review

Evelin must personally review all ten Grype findings and choose a justified VEX status for each. The included VEX statements intentionally remain `under_investigation`; proposed dispositions in the checklist are not approvals.

The findings are CVE-2026-11940, CVE-2026-11972, CVE-2026-15308, CVE-2026-3298, CVE-2026-3644, CVE-2026-4224, CVE-2026-4786, CVE-2026-6100, CVE-2026-7210, and CVE-2026-9669.

Review `evelin-security-review-checklist.md` for the upstream advisory, affected-code assessment, runtime reachability, mitigation evidence, proposed state, and remaining risk for every finding.

## Validation already recorded

- Isolated verifier and contract tests: 24 passed.
- Trivy High/Critical: 0.
- Grype High/Critical: 10 CPython version-metadata findings; 0 fixes published for Python 3.12 according to the captured scan.
- Candidate evidence Gitleaks: no candidate secret findings; this PR is rescanned before publication.
- VEX: unsigned and under investigation.
- Cosign: not run.
- Image publication and deployment: not performed.

## Protected signing controls

The `security-owner-signing` environment requires reviewer `kazan555` (user ID `77101516`), prevents self-review, and disables administrator bypass. The decision workflow is pinned to `refs/heads/main`, uses `contents: read` and `id-token: write`, validates the exact PR head and evidence hashes, and binds any eventual keyless signature to its GitHub Actions workflow identity. No signing workflow is triggered by this draft PR.

## Files

- `evelin-security-review-checklist.md`: plain-language ten-finding checklist and independent signing procedure.
- `openvex-draft.json`: unsigned OpenVEX draft; all ten statements remain under investigation.
- `security-owner-record.json`: Evelin/kazan555 identity and exact subject binding.
- `subject.json`: immutable image, source, SBOM, OpenAPI, contract, and test identifiers.
- `scanner-summary.json`: exact scanner counts and finding IDs.
- `provenance-attestation-request.json`: unsigned provenance request.
- `cosign-verification-policy.json`: issuer, workflow identity, digest, and required-attestation policy.
- `protected-environment-summary.json`: required reviewer and protected OIDC job controls observed through GitHub and workflow source.
- `SHA256SUMS`: deterministic checksum manifest for every review file except itself.

Do not mark this PR ready, approve it on Evelin's behalf, merge it, sign the image, publish the image, or deploy it as part of this review-package change.

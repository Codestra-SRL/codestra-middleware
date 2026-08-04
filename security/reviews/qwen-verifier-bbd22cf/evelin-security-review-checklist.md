# Evelin Appolon — independent Qwen verifier security checklist

This is an unsigned review worksheet. Completing it does not deploy or sign the container.

## Exact subject

- Candidate commit: `bbd22cf7a9ff1dd7d6ef12504d21031bc1f5ab75`
- Image digest: `sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef`
- SBOM SHA-256: `380c366db3c70f743a675285cff7665d2ea86523f5967b76d53293a61b1f09ec`
- Registry requested: `ghcr.io/Codestra-SRL/qwen-auth-verifier`
- Canonical OCI subject (repository components normalized to lowercase): `ghcr.io/codestra-srl/qwen-auth-verifier@sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef`
- Signing mechanism: GitHub Actions OIDC keyless Cosign
- Release Owner: Ralph Appolon
- Security Owner: Evelin Appolon
- Security Owner GitHub username: `kazan555`
- Immutable GitHub user ID: `77101516`
- Verified repository permission: `admin` on `Codestra-SRL/codestra-middleware`
- Existing protected reviewer: `kazan555` on `security-owner-signing` (preserved)
- Rollback Authority: Ralph Appolon

The VEX remains `under_investigation` until Evelin personally records and signs a decision through the approved independent workflow.

## Before reviewing findings

- [ ] Verify the archive SHA-256 supplied with the package.
- [ ] Run `sha256sum -c MANIFEST.sha256` from the extracted package root.
- [ ] Verify `scanner/sbom.cdx.json` hashes to the SBOM value above.
- [ ] Verify the image digest, candidate commit, and SBOM hash occur in every JSON governance record.
- [ ] Confirm `tests/pytest.txt` reports 24 passing tests.
- [ ] Confirm `scanner/trivy-after-review.json` contains zero High/Critical findings.
- [ ] Confirm `scanner/grype-after-review.json` contains exactly the ten findings below.
- [ ] Read `vex/grype-cpython-review.md`, the Dockerfile backport list, and `security/python312/README.md` from candidate commit `bbd22cf7a9ff1dd7d6ef12504d21031bc1f5ab75`.

## Finding decisions

For every row, choose approve, reject, or request-more-evidence. Do not approve solely because runtime reachability is low; first verify the cited patch is actually incorporated into the immutable image lineage.

- [ ] **CVE-2026-11940 — tarfile hardlink escape.** Proposed state: `fixed`. Evidence: checksum-pinned CPython 3.12 backport `be13e86f6b9788a6f4d0419dffef72cbae5865c9`; no archive route/import. Remaining risk: source-backport equivalence and behavior in this exact binary require independent acceptance.
- [ ] **CVE-2026-11972 — streaming tar CPU denial of service.** Proposed state: `fixed`. Evidence: backport `7f0dc59c9a70f8f3b4da33d7c4a2ba552a7acc21`; no streaming-tar handling. Remaining risk: scanner cannot infer source backports from version metadata.
- [ ] **CVE-2026-15308 — incremental HTML parser CPU denial of service.** Proposed state: `fixed`. Evidence: backport `7933f4bf7131aa4140750f9404f5de0aa2969ced`; verifier hashes request bytes and does not parse HTML. Remaining risk: the standard-library module remains present.
- [ ] **CVE-2026-3298 — Windows ProactorEventLoop buffer write.** Proposed state: `not_affected/component_not_present`. Evidence: upstream advisory states Windows-only; immutable image reports Linux/amd64. Remaining risk: approve only after independently verifying the image platform and absence of a Windows artifact substitution.
- [ ] **CVE-2026-3644 — cookie control-character validation bypass.** Proposed state: `fixed`. Evidence: backport `dae4b1a21f8df4570e30986affd61bbe4ade4cef`; verifier does not consume or emit cookies. Remaining risk: HTTP framework dependencies are present even though this route does not use cookie APIs.
- [ ] **CVE-2026-4224 — Expat nested model stack overflow.** Proposed state: `fixed`. Evidence: backport `642865ddf4b232da1f3b1f7abcfa3254c4bfe785`; verifier accepts no XML. Remaining risk: Expat is present and must remain correctly patched.
- [ ] **CVE-2026-4786 — webbrowser command injection bypass.** Proposed state: `fixed`. Evidence: checksum-pinned 3.12 adaptation of upstream `f4654824ae0850ac87227fb270f9057477946769`; verifier contains no browser, shell, subprocess, or command facility. Remaining risk: the mitigation is a local 3.12 adaptation and deserves direct diff review.
- [ ] **CVE-2026-6100 — decompressor use-after-free after MemoryError.** Proposed state: `fixed`. Evidence: backport `e20c6c9667c99ecaab96e1a2b3767082841ffc8b`; verifier performs no decompression. Remaining risk: compression modules remain installed.
- [ ] **CVE-2026-7210 — Expat hash-flooding entropy.** Proposed state: `fixed`. Evidence: Expat 2.8.2, local 3.12 entropy adaptation, and upstream remainder `fc9b11ff49cbc82e6f917d07a61517a2b5f3145f`. Remaining risk: this combines a library pin with a local adaptation and therefore needs both pieces independently verified.
- [ ] **CVE-2026-9669 — BZ2 decompressor invalid-state write.** Proposed state: `fixed`. Evidence: 3.12 backport contained in `938ec030e90c5e53f1faac6fab1643f14e4f4a79`; verifier performs no decompression. Remaining risk: the vulnerable module remains present and the scanner sees only version 3.12.13.

## Cross-cutting decision checks

- [ ] Confirm the OpenVEX draft has ten statements and every current status is `under_investigation`.
- [ ] Decide whether source-backport evidence is sufficient or whether exact-binary behavioral regression evidence is required before changing any proposed state to `fixed`.
- [ ] Confirm there are zero fixable High/Critical findings for Python 3.12 according to both scanner reports.
- [ ] Confirm the dedicated runtime contains only the verifier application module and exposes no downstream, command, workflow, or database route.
- [ ] Record residual risk explicitly; do not convert a proposed disposition into an approval by inference.

## Exact independent signing procedure

Do not run these commands on this middleware host. GitHub user `kazan555` (immutable user ID `77101516`) is the verified account for Evelin Appolon, already has `admin` permission on the exact repository, and is already the protected reviewer required by the workflow. Preserve that configuration.

Evelin must personally approve the protected `security-owner-signing` environment as `kazan555` for `.github/workflows/security-owner-decision-sign.yml` on `refs/heads/main`. The workflow—not a locally generated key—must execute:

```sh
cosign sign-blob --yes \
  --bundle security-owner-decision.sigstore.json \
  security-owner-decision.json

cosign verify-blob \
  --bundle security-owner-decision.sigstore.json \
  --certificate-identity 'https://github.com/Codestra-SRL/codestra-middleware/.github/workflows/security-owner-decision-sign.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  security-owner-decision.json
```

Before signing, Evelin must confirm the canonical decision document contains all three exact subject values at the top of this checklist, GitHub username `kazan555`, immutable user ID `77101516`, a decision for every CVE, an explicit residual-risk statement, and a fresh UTC decision timestamp. She must also verify that the workflow approval audit records `kazan555` as approver, records a different requestor, reports `self_review=false`, and reports `bypass_used=false`.

Signing the Security Owner decision does not sign the container and does not authorize deployment. Container signing and deployment remain separate Release Owner and deployment gates.

If the independent decision is approved and the Release Owner separately authorizes image signing, the approved `sign-middleware-release.yml` workflow must use this exact immutable subject:

```sh
cosign sign --yes \
  'ghcr.io/codestra-srl/qwen-auth-verifier@sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef'

cosign verify \
  --certificate-identity 'https://github.com/Codestra-SRL/codestra-middleware/.github/workflows/sign-middleware-release.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  'ghcr.io/codestra-srl/qwen-auth-verifier@sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef'
```

These image commands are instructions only and were not executed while preparing this package.

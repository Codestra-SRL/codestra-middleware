# Wave 3 release evidence

This package binds evidence to Middleware source commit
`b9bd495ef65272463803b721698e5645316959cc` and local OCI digest
`sha256:9417dc4d6b489e157580d746e8edda66678f5c7cf8beb5a565f73f6ded654215`.

The package is preparatory and does not authorize release. The image is not
published at the approved GHCR repository, the source is not on protected
`main`, and the required independent Security Owner decision, Cosign signature,
transparency-log entry, attestations, and independent verification are absent.

`openvex.json` records every Grype High finding as `under_investigation`. It
does not suppress, waive, or declare any finding `not_affected`.

The protected release workflow may run only after the reviewed source is on
`main`, the exact digest is published to the allowlisted repository, and a real
Security Owner decision satisfies the workflow's fail-closed evidence checks.

Raw Trivy, Grype, and image-inspection JSON remains in the root-only local
evidence directory. It is represented here by SHA-256 in
`release-evidence-report.json`; the raw scanner output is intentionally excluded
from Git because deterministic package digests trigger generic-secret rules.

Odoo delivery remains disabled. No staging or production database, service, or
credential was changed while generating this package.

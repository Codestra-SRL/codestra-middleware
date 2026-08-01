# Security Owner decision signing workflow

The workflow accepts only a PR number, exact PR head, and repository-relative paths plus SHA-256 values for a decision request and image manifest. It fetches those files as inert data and never checks out or executes PR-controlled code.

Validation code and the workflow are loaded from protected `main`. The signing job has read-only repository permissions plus `id-token: write`, requires independent approval by `kazan555` in `security-owner-signing`, generates timestamps at runtime, creates a keyless Sigstore bundle, and verifies the exact workflow identity and GitHub Actions issuer immediately.

The signed scope is staging preparation only. Staging deployment, production deployment and activation, Server B, customer data, telephony, recordings, public ingress, and n8n activation remain blocked.

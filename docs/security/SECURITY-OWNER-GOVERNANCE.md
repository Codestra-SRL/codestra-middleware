# Security Owner governance

The approval delegate recorded in `SECURITY.md` may accept only digest-bound risks for Server A isolated-staging preparation. Approval does not authorize staging deployment, production deployment or activation, Server B, customer data, telephony, communications, or recordings.

The signing workflow runs only from protected `main`, uses the `security-owner-signing` environment, records the independent environment approval, and signs canonical bytes with GitHub Actions OIDC. Code review, environment approval, and Sigstore verification are separate mandatory records.

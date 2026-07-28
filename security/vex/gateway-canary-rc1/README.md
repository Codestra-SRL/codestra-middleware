# Bounded Canary Gateway RC1 Security Binding

This directory binds the reviewed bounded-canary gateway source, immutable
Docker Hub digest, SBOMs, scanner evidence, fixed-backport decision, and
OpenVEX statements.

The signing workflow runs only from `main`, signs the exact image identity with
`--upload=false`, signs the exact OpenVEX document, and independently verifies
both Sigstore bundles. It does not deploy the image or mutate production.

# Section 11 — Enterprise security and governance

The cross-domain gate is deterministic and fail-closed. Access requires both
RBAC and ABAC decisions, exact tenant/workspace scope, and MFA when required.
Requester, approver, and reviewer identities must be distinct for separated
duties. Audit records require actor, scope, action, subject, decision,
correlation, and redacted payload evidence.

Security readiness fails on any unresolved HIGH or CRITICAL finding, unknown
security domain, or incomplete evidence. Supply-chain readiness requires pinned
source, signed artifact, SBOM, dependency scan, container scan, and secret scan.
Secrets are represented only by protected references; raw values are forbidden
in code, logs, prompts, exports, and evidence.

Data classification supports PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, PHI,
PCI, and SECRET. Purpose approval and legal-hold state are explicit. Compliance
readiness is evidence-based for SOC 2, ISO 27001, HIPAA-ready, GDPR-ready,
CCPA-ready, and PCI segmentation controls where applicable.

This section does not enable production autonomy, external writes, live payment,
telephony, trading, workflow activation, or automatic emergency re-enable.

Secret scanning uses the repository `.gitleaks.toml` allowlist only for reviewed
hashes and synthetic identifiers. It does not allow runtime secret files,
environment files, credentials, private keys, or arbitrary API-key patterns.

The Docker build upgrades pip to a fixed secure release before installing the
pinned application dependencies. Existing immutable images are not mutated in
place; they must be rebuilt and rescanned before promotion. The staging image
scan remains a release gate until that rebuild is completed.

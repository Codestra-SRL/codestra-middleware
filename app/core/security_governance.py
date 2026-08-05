"""Cross-domain Section 11 security, governance, and compliance gates."""

from dataclasses import dataclass

SECURITY_DOMAINS = frozenset({
    "IDENTITY", "MFA", "RBAC", "ABAC", "SECRETS", "ENCRYPTION", "KEY_ROTATION",
    "CERTIFICATES", "CONFIGURATION", "VULNERABILITY", "DEPENDENCIES", "SBOM",
    "SUPPLY_CHAIN", "CONTAINER", "RUNTIME", "NETWORK", "DATABASE", "API", "AI",
    "VOICE", "MARKETPLACE", "AUDIT", "GOVERNANCE", "COMPLIANCE",
})
COMPLIANCE_FRAMEWORKS = frozenset({"SOC2", "ISO27001", "HIPAA_READY", "GDPR_READY", "CCPA_READY", "PCI_SEGMENTATION"})
SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"})
CLASSIFICATIONS = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PHI", "PCI", "SECRET"})


@dataclass(frozen=True)
class AccessDecision:
    tenant_id: str
    workspace_id: str
    record_tenant_id: str
    record_workspace_id: str
    role_allowed: bool
    attributes_allowed: bool
    mfa_required: bool = False
    mfa_verified: bool = False


@dataclass(frozen=True)
class SeparationOfDuties:
    requester_id: str
    approver_id: str
    reviewer_id: str
    requester_approved: bool
    approver_approved: bool
    reviewer_approved: bool


@dataclass(frozen=True)
class AuditRecord:
    actor_id: str
    tenant_id: str
    workspace_id: str
    action: str
    subject: str
    decision: str
    correlation_id: str
    redacted: bool


@dataclass(frozen=True)
class SupplyChainEvidence:
    source_pinned: bool
    artifact_signed: bool
    sbom_present: bool
    dependency_scan_passed: bool
    container_scan_passed: bool
    secret_scan_passed: bool


def authorize_access(decision: AccessDecision) -> tuple[bool, str]:
    required = (decision.tenant_id, decision.workspace_id, decision.record_tenant_id, decision.record_workspace_id)
    if not all(required):
        return False, "MISSING_SCOPE"
    if decision.tenant_id != decision.record_tenant_id or decision.workspace_id != decision.record_workspace_id:
        return False, "SCOPE_MISMATCH"
    if not decision.role_allowed or not decision.attributes_allowed:
        return False, "AUTHORIZATION_DENIED"
    if decision.mfa_required and not decision.mfa_verified:
        return False, "MFA_REQUIRED"
    return True, "AUTHORIZED"


def separation_of_duties_valid(value: SeparationOfDuties) -> bool:
    if not all((value.requester_id, value.approver_id, value.reviewer_id)):
        return False
    if len({value.requester_id, value.approver_id, value.reviewer_id}) != 3:
        return False
    return value.requester_approved and value.approver_approved and value.reviewer_approved


def audit_record_valid(value: AuditRecord) -> bool:
    required = (value.actor_id, value.tenant_id, value.workspace_id, value.action, value.subject, value.decision, value.correlation_id)
    return bool(all(required) and value.redacted)


def security_gate(*, findings: list[tuple[str, str]], domains: set[str], evidence_complete: bool) -> tuple[bool, str]:
    if not domains.issubset(SECURITY_DOMAINS) or not domains:
        return False, "UNKNOWN_SECURITY_DOMAIN"
    if any(severity in {"CRITICAL", "HIGH"} for _, severity in findings):
        return False, "UNRESOLVED_HIGH_OR_CRITICAL_FINDING"
    if not evidence_complete:
        return False, "EVIDENCE_INCOMPLETE"
    return True, "PASS"


def compliance_gate(*, frameworks: set[str], controls_complete: bool, audit_complete: bool, retention_defined: bool) -> tuple[bool, str]:
    if not frameworks or not frameworks.issubset(COMPLIANCE_FRAMEWORKS):
        return False, "INVALID_FRAMEWORK"
    if not (controls_complete and audit_complete and retention_defined):
        return False, "COMPLIANCE_EVIDENCE_INCOMPLETE"
    return True, "READY"


def classification_allowed(classification: str, *, purpose_approved: bool, legal_hold: bool = False) -> bool:
    return classification in CLASSIFICATIONS and purpose_approved and not (classification == "SECRET" and not legal_hold)


def secret_reference_safe(*, reference: str, raw_secret_present: bool) -> bool:
    return bool(reference and not raw_secret_present and not any(token in reference.lower() for token in ("password=", "secret=", "token=")))


def supply_chain_gate(evidence: SupplyChainEvidence) -> bool:
    return all((evidence.source_pinned, evidence.artifact_signed, evidence.sbom_present, evidence.dependency_scan_passed, evidence.container_scan_passed, evidence.secret_scan_passed))

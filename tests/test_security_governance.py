from app.core.security_governance import AccessDecision, AuditRecord, SeparationOfDuties, SupplyChainEvidence, authorize_access, audit_record_valid, classification_allowed, compliance_gate, secret_reference_safe, security_gate, separation_of_duties_valid, supply_chain_gate


def test_access_requires_rbac_abac_scope_and_mfa():
    base = dict(tenant_id="t1", workspace_id="w1", record_tenant_id="t1", record_workspace_id="w1", role_allowed=True, attributes_allowed=True)
    assert authorize_access(AccessDecision(**base)) == (True, "AUTHORIZED")
    assert authorize_access(AccessDecision(**{**base, "record_tenant_id": "t2"}))[1] == "SCOPE_MISMATCH"
    assert authorize_access(AccessDecision(**{**base, "mfa_required": True}))[1] == "MFA_REQUIRED"


def test_sod_and_audit_are_explicit():
    assert separation_of_duties_valid(SeparationOfDuties("requester", "approver", "reviewer", True, True, True))
    assert not separation_of_duties_valid(SeparationOfDuties("same", "same", "reviewer", True, True, True))
    assert audit_record_valid(AuditRecord("u1", "t1", "w1", "approve", "release-1", "APPROVED", "trace-1", True))
    assert not audit_record_valid(AuditRecord("u1", "t1", "w1", "approve", "release-1", "APPROVED", "trace-1", False))


def test_security_compliance_supply_chain_and_data_gates_fail_closed():
    assert security_gate(findings=[("x", "MEDIUM")], domains={"API", "AI"}, evidence_complete=True) == (True, "PASS")
    assert security_gate(findings=[("x", "HIGH")], domains={"API"}, evidence_complete=True)[1] == "UNRESOLVED_HIGH_OR_CRITICAL_FINDING"
    assert compliance_gate(frameworks={"SOC2", "ISO27001"}, controls_complete=True, audit_complete=True, retention_defined=True) == (True, "READY")
    assert classification_allowed("CONFIDENTIAL", purpose_approved=True)
    assert not classification_allowed("SECRET", purpose_approved=True)
    assert secret_reference_safe(reference="vault://codestra/odoo", raw_secret_present=False)
    assert not secret_reference_safe(reference="password=leaked", raw_secret_present=False)
    assert supply_chain_gate(SupplyChainEvidence(True, True, True, True, True, True))
    assert not supply_chain_gate(SupplyChainEvidence(True, True, True, True, False, True))

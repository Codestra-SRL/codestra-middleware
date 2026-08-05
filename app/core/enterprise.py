"""Fail-closed contracts for enterprise IAM, governance, integrations, data, and DR."""
from dataclasses import dataclass


class EnterprisePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class IdentityAssertion:
    tenant_id: str
    subject: str
    issuer: str
    audience: str
    nonce_valid: bool
    replayed: bool = False


@dataclass(frozen=True)
class WebhookDecision:
    tenant_id: str
    signature_valid: bool
    replayed: bool
    idempotency_key: str


@dataclass(frozen=True)
class DataAccess:
    tenant_id: str
    row_tenant_id: str
    role_allowed: bool


@dataclass(frozen=True)
class BackupEvidence:
    service: str
    encrypted: bool
    off_server: bool
    checksum_valid: bool
    restore_tested: bool


def validate_identity(assertion: IdentityAssertion) -> bool:
    return bool(assertion.tenant_id and assertion.subject and assertion.issuer and assertion.audience and assertion.nonce_valid and not assertion.replayed)


def accept_webhook(decision: WebhookDecision) -> bool:
    return bool(decision.tenant_id and decision.signature_valid and not decision.replayed and decision.idempotency_key)


def authorize_data_access(access: DataAccess) -> bool:
    return bool(access.tenant_id and access.row_tenant_id and access.tenant_id == access.row_tenant_id and access.role_allowed)


def validate_backup(evidence: BackupEvidence) -> bool:
    return bool(evidence.service and evidence.encrypted and evidence.off_server and evidence.checksum_valid and evidence.restore_tested)

"""Fail-closed enterprise IAM policy primitives.

Identity proof is delegated to the configured OIDC provider.  This module only
accepts validated claims and never trusts tenant, workspace, role, or permission
headers supplied by a caller.
"""

from dataclasses import dataclass
from typing import Any


class IAMAuthorizationError(ValueError):
    """Raised when validated identity claims do not authorize an operation."""


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "platform_owner": frozenset({"*"}),
    "platform_admin": frozenset({"identity.read", "identity.write", "audit.read", "event.read", "event.publish", "event.replay"}),
    "security_admin": frozenset(
        {"identity.read", "identity.write", "policy.manage", "audit.read", "session.revoke", "event.read", "event.replay"}
    ),
    "tenant_owner": frozenset({"identity.read", "identity.write", "workspace.manage"}),
    "tenant_admin": frozenset({"identity.read", "identity.write", "workspace.manage"}),
    "department_manager": frozenset({"identity.read", "department.manage"}),
    "supervisor": frozenset({"identity.read", "voice.read"}),
    "agent": frozenset({"crm.read", "crm.write", "voice.read"}),
    "customer": frozenset({"portal.read"}),
    "api_client": frozenset(),
    "ai_employee": frozenset({"memory.read", "knowledge.search"}),
    "auditor": frozenset({"audit.read"}),
    "compliance": frozenset({"audit.read", "compliance.read", "compliance.write"}),
    "developer": frozenset({"workflow.execute", "development.read"}),
    "read_only": frozenset({"identity.read"}),
}


@dataclass(frozen=True)
class IdentityContext:
    subject: str
    tenant_id: str
    workspace_id: str
    department_ids: frozenset[str]
    roles: frozenset[str]
    permissions: frozenset[str]
    session_id: str

    @classmethod
    def from_validated_claims(cls, claims: dict[str, Any]) -> "IdentityContext":
        required = ("sub", "tenant_id", "workspace_id", "sid")
        if any(not isinstance(claims.get(key), str) or not claims[key] for key in required):
            raise IAMAuthorizationError("required identity claim missing")
        roles = _string_set(claims.get("roles", []), "roles")
        unknown = roles.difference(ROLE_PERMISSIONS)
        if unknown:
            raise IAMAuthorizationError("unknown role denied")
        explicit_permissions = _string_set(claims.get("permissions", []), "permissions")
        granted = set(explicit_permissions)
        for role in roles:
            granted.update(ROLE_PERMISSIONS[role])
        return cls(
            subject=claims["sub"],
            tenant_id=claims["tenant_id"],
            workspace_id=claims["workspace_id"],
            department_ids=_string_set(claims.get("department_ids", []), "department_ids"),
            roles=roles,
            permissions=frozenset(granted),
            session_id=claims["sid"],
        )

    def require_scope(self, tenant_id: str, workspace_id: str) -> None:
        if tenant_id != self.tenant_id or workspace_id != self.workspace_id:
            raise IAMAuthorizationError("resource scope denied")

    def require_permission(self, permission: str) -> None:
        if "*" not in self.permissions and permission not in self.permissions:
            raise IAMAuthorizationError("permission denied")


def _string_set(value: Any, label: str) -> frozenset[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise IAMAuthorizationError(f"{label} claim invalid")
    return frozenset(value)

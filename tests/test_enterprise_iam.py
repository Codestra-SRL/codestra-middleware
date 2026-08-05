import pytest

from app.core.iam import IAMAuthorizationError, IdentityContext


def claims(**updates):
    value = {
        "sub": "user-1",
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "department_ids": ["department-a"],
        "roles": ["tenant_admin"],
        "permissions": [],
        "sid": "session-1",
    }
    value.update(updates)
    return value


def test_identity_is_derived_only_from_validated_claims():
    identity = IdentityContext.from_validated_claims(claims())
    assert identity.tenant_id == "tenant-a"
    assert "identity.write" in identity.permissions


@pytest.mark.parametrize("missing", ["sub", "tenant_id", "workspace_id", "sid"])
def test_required_identity_claims_fail_closed(missing):
    value = claims()
    value.pop(missing)
    with pytest.raises(IAMAuthorizationError):
        IdentityContext.from_validated_claims(value)


def test_unknown_role_fails_closed():
    with pytest.raises(IAMAuthorizationError):
        IdentityContext.from_validated_claims(claims(roles=["made_up_admin"]))


def test_cross_tenant_and_workspace_access_is_denied():
    identity = IdentityContext.from_validated_claims(claims())
    with pytest.raises(IAMAuthorizationError):
        identity.require_scope("tenant-b", "workspace-a")
    with pytest.raises(IAMAuthorizationError):
        identity.require_scope("tenant-a", "workspace-b")


def test_ai_employee_has_no_write_or_tool_permission():
    identity = IdentityContext.from_validated_claims(claims(roles=["ai_employee"]))
    with pytest.raises(IAMAuthorizationError):
        identity.require_permission("crm.write")
    with pytest.raises(IAMAuthorizationError):
        identity.require_permission("workflow.execute")

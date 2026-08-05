import pytest
from fastapi import HTTPException

from app.core.customer_portal import require_customer_scope


def test_customer_scope_accepts_customer_role():
    assert require_customer_scope("tenant-a", "CUSTOMER_ANALYST") == ("tenant-a", "CUSTOMER_ANALYST")


@pytest.mark.parametrize("tenant,role", [("", "CUSTOMER_ADMIN"), ("tenant-a", "AI_PLATFORM_ADMIN"), ("tenant-a", "")])
def test_customer_scope_rejects_missing_or_internal_roles(tenant, role):
    with pytest.raises(HTTPException) as exc:
        require_customer_scope(tenant, role)
    assert exc.value.status_code == 403

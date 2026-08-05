import pytest
from fastapi import HTTPException

from app.api.v1.operations import require_ops_role


def test_operations_role_guard_is_fail_closed():
    require_ops_role("AI_PLATFORM_ADMIN")
    require_ops_role("AI_AUDITOR")
    with pytest.raises(HTTPException) as exc:
        require_ops_role("AI_READ_ONLY")
    assert exc.value.status_code == 403

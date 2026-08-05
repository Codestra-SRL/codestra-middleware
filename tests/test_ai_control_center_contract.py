import pytest
from fastapi import HTTPException

from app.api.v1.ai_control_center import _guard


def test_control_center_guard_allows_platform_read_roles():
    _guard("AI_PLATFORM_ADMIN", "ai.overview.read")
    _guard("AI_READ_ONLY", "health.read")


def test_control_center_guard_rejects_unknown_roles():
    with pytest.raises(HTTPException) as exc:
        _guard("UNTRUSTED", "ai.overview.read")
    assert exc.value.status_code == 403

import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1.security_governance import overview


def test_security_governance_overview_is_role_gated_and_read_only():
    value = asyncio.run(overview(role="SECURITY_AUDITOR"))
    assert value["mode"] == "read_only_evidence"
    assert value["production_actions"] is False
    with pytest.raises(HTTPException) as exc:
        asyncio.run(overview(role="CUSTOMER_READ_ONLY"))
    assert exc.value.status_code == 403

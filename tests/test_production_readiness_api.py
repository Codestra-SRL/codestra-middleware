import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1.production_readiness import overview


def test_readiness_overview_is_role_gated_and_non_activating():
    response = asyncio.run(overview(role="EXECUTIVE_READ_ONLY"))
    assert response["production_activation"] is False
    assert response["automatic_deployment"] is False
    with pytest.raises(HTTPException) as exc:
        asyncio.run(overview(role="CUSTOMER_READ_ONLY"))
    assert exc.value.status_code == 403

import pytest
from fastapi import HTTPException

from app.api.v1.bi import require_bi
from app.core.bi import kpi_contract


def test_kpi_contract_is_explicit_and_source_backed():
    contract = kpi_contract("revenue")
    assert contract.source == "odoo.account.move"
    assert contract.definition


def test_bi_access_is_fail_closed_for_unknown_role():
    with pytest.raises(HTTPException) as exc:
        require_bi("CUSTOMER_READ_ONLY")
    assert exc.value.status_code == 403

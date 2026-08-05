import pytest
from fastapi import HTTPException

from app.api.v1.saas import require_saas
from app.core.saas import PLAN_CONTRACTS, quota_outcome


def test_plan_contracts_are_versionable_and_have_entitlements():
    assert len(PLAN_CONTRACTS) == 4
    assert all(plan.code and plan.entitlements for plan in PLAN_CONTRACTS)


@pytest.mark.parametrize("used,allowance,expected", [(0, 100, "ALLOWED"), (80, 100, "WARNING"), (100, 100, "HARD_LIMIT_REACHED"), (1, 0, "HARD_LIMIT_REACHED")])
def test_quota_outcomes_are_fail_closed(used, allowance, expected):
    assert quota_outcome(used, allowance) == expected


def test_saas_role_guard_rejects_customer_read_only():
    with pytest.raises(HTTPException) as exc:
        require_saas("CUSTOMER_READ_ONLY")
    assert exc.value.status_code == 403

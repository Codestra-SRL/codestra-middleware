from uuid import uuid4

import pytest

from app.adapters.odoo.lead_automation import PermanentApplyError
from app.core.reliability import RetryPolicy
from app.workers import scraper_odoo_delivery
from app.workers.outbox import record_failure


def test_worker_classifies_odoo_contract_errors_as_permanent() -> None:
    assert scraper_odoo_delivery._permanent_failure(PermanentApplyError("denied"))


def test_worker_does_not_classify_transport_errors_as_permanent() -> None:
    assert not scraper_odoo_delivery._permanent_failure(TimeoutError())


class _Result:
    rowcount = 1


class _Session:
    def __init__(self) -> None:
        self.parameters = None
        self.committed = False

    async def execute(self, _statement, parameters):
        self.parameters = parameters
        return _Result()

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_permanent_failure_dead_letters_on_first_attempt() -> None:
    session = _Session()
    status = await record_failure(
        session,
        uuid4(),
        0,
        "PermanentApplyError",
        RetryPolicy(max_attempts=8, base_seconds=1, max_seconds=60),
        permanent=True,
    )
    assert status == "dead_letter"
    assert session.parameters["attempts"] == 1
    assert session.parameters["next_attempt_at"] is None
    assert session.parameters["dead_lettered_at"] is not None
    assert session.committed

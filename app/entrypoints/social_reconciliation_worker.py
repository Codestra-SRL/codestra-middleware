from app.core.config import settings
from app.db.session import SessionFactory
from app.entrypoints.runtime import run_worker
from app.workers.social import recover_expired_reconciliation_leases

SERVICE = "middleware-social-reconciliation-worker"
QUEUE = "middleware.social.reconciliation.v1"


async def cycle() -> dict[str, object]:
    if not settings.social_reconciliation_worker_enabled:
        return {"status": "disabled"}
    if settings.postly_adapter_enabled:
        return {"status": "provider_reconciliation_not_authorized"}
    async with SessionFactory() as session:
        recovered = await recover_expired_reconciliation_leases(session)
        return {"status": "mock_only", "recovered_leases": recovered}


if __name__ == "__main__":
    run_worker(SERVICE, QUEUE, cycle)

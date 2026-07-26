"""Report-only reconciliation worker."""
from app.db.session import SessionFactory
from app.entrypoints.runtime import run_worker
from app.workers.reconciliation import reconcile_internal_outbox


SERVICE = "middleware-reconciliation-worker"
QUEUE = "middleware.reconciliation.v1"


async def cycle() -> dict[str, object]:
    async with SessionFactory() as session:
        return await reconcile_internal_outbox(session)


if __name__ == "__main__":
    run_worker(SERVICE, QUEUE, cycle)

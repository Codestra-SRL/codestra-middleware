"""External outbox delivery worker; disabled unless explicitly enabled."""
from app.db.session import SessionFactory
from app.core.config import settings
from app.entrypoints.runtime import run_worker
from app.workers.outbox import acknowledge, claim_batch, record_failure
from app.workers.outbox_dispatcher import dispatch
from app.core.reliability import RetryPolicy


SERVICE = "middleware-notification-worker"
QUEUE = "middleware.notification.v1"


async def cycle() -> dict[str, object]:
    enabled = settings.outbox_processing_active and (settings.messaging_enabled or settings.n8n_delivery_enabled or settings.odoo_delivery_enabled)
    if not enabled:
        return {"status": "disabled"}
    delivered = retried = dead_lettered = 0
    async with SessionFactory() as session:
        claimed = await claim_batch(session, limit=50, lease_seconds=settings.outbox_lease_seconds)
        policy = RetryPolicy(max_attempts=settings.outbox_max_attempts, base_seconds=settings.outbox_base_delay_seconds, max_seconds=settings.outbox_max_delay_seconds)
        for item in claimed:
            result = await dispatch(
                item["payload"], item["topic"], str(item["id"])
            )
            if result.outcome == "delivered":
                await acknowledge(session, item["id"], result.response)
                delivered += 1
                continue
            if result.outcome == "permanent":
                status = await record_failure(session, item["id"], settings.outbox_max_attempts - 1, result.error or "target rejected request", policy)
            else:
                status = await record_failure(session, item["id"], int(item["attempts"]), result.error or "target unavailable", policy)
            if status == "dead_letter":
                dead_lettered += 1
            else:
                retried += 1
    return {"status": "idle", "claimed": len(claimed), "delivered": delivered, "retried": retried, "dead_lettered": dead_lettered}


if __name__ == "__main__":
    run_worker(SERVICE, QUEUE, cycle)

from app.core.config import settings
from app.db.session import SessionFactory
from app.entrypoints.runtime import run_worker
from app.workers.social import claim_delivery, complete_mock_delivery

SERVICE = "middleware-social-delivery-worker"
QUEUE = "middleware.social.delivery.v1"


async def cycle() -> dict[str, object]:
    if not settings.social_delivery_worker_enabled:
        return {"status": "disabled"}
    if not settings.social_mock_adapter_enabled or settings.postly_adapter_enabled:
        return {"status": "kill_switch_closed"}
    async with SessionFactory() as session:
        item = await claim_delivery(session, SERVICE)
        if not item:
            return {"status": "idle"}
        await complete_mock_delivery(session, item["id"])
        return {"status": "mock_scheduled", "publication_id": str(item["id"])}


if __name__ == "__main__":
    run_worker(SERVICE, QUEUE, cycle)

from app.core.config import settings
from app.db.session import SessionFactory
from app.entrypoints.runtime import run_worker
from app.workers.social import dead_letter_depth, recover_expired_delivery_leases

SERVICE = "middleware-social-dead-letter-worker"
QUEUE = "middleware.social.dead-letter.v1"


async def cycle() -> dict[str, object]:
    if not settings.social_control_plane_enabled:
        return {"status": "disabled"}
    async with SessionFactory() as session:
        recovered = await recover_expired_delivery_leases(session)
        depth = await dead_letter_depth(session)
        return {
            "status": "report_only"
            if not settings.social_dead_letter_replay_enabled
            else "replay_enabled",
            "recovered_leases": recovered,
            "dead_letter_depth": depth,
        }


if __name__ == "__main__":
    run_worker(SERVICE, QUEUE, cycle)

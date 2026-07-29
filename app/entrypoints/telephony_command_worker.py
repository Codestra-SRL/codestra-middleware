"""Registered telephony command worker entrypoint.

Runtime composition supplies the registry-backed client.  The deployment flag
defaults false, so source merge alone cannot dispatch a command.
"""

from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionFactory
from app.entrypoints.runtime import run_worker
from app.workers.telephony_commands import TelephonyDispatcher, dispatch_one

SERVICE = "middleware-telephony-command-worker"
QUEUE = "telephony-commands"
_client_factory: Callable[[AsyncSession], TelephonyDispatcher] | None = None


def configure_client_factory(
    factory: Callable[[AsyncSession], TelephonyDispatcher],
) -> None:
    global _client_factory
    _client_factory = factory


async def cycle() -> dict[str, object]:
    if not settings.telephony_command_worker_enabled:
        return {"claimed": 0, "disabled": True}
    if _client_factory is None:
        raise RuntimeError("telephony command client factory is not configured")
    return await dispatch_one(
        SessionFactory,
        _client_factory,
        traceparent_factory=lambda: (
            "00-" + uuid4().hex + "-" + uuid4().hex[:16] + "-01"
        ),
    )


def main() -> None:
    run_worker(SERVICE, QUEUE, cycle)


if __name__ == "__main__":
    main()

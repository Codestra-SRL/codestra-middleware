"""Fail-closed Wave 3 worker entrypoint.

The production adapter is intentionally absent from Wave 3. This entrypoint can
only recover expired leases until separately reviewed delivery support exists.
"""

import asyncio

from app.core.config import settings
from app.db.session import SessionFactory
from app.workers.odoo_business import recover_expired_leases


async def run_once() -> dict[str, int]:
    if settings.odoo_delivery_enabled or settings.odoo_automation_writes_enabled:
        raise RuntimeError("Odoo business delivery is not authorized in Wave 3")
    async with SessionFactory() as session:
        return await recover_expired_leases(session)


def main() -> None:
    asyncio.run(run_once())


if __name__ == "__main__":
    main()

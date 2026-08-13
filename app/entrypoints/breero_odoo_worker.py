"""Disabled-by-default BREERO Odoo outbox worker."""

import asyncio

from app.entrypoints.runtime import configure_logging, validate_runtime
from app.workers.breero_odoo_delivery import run_forever


def main() -> None:
    configure_logging()
    validate_runtime("middleware-breero-odoo-worker")
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()

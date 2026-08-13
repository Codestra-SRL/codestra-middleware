"""Staging-only scraper to Odoo delivery worker."""

import asyncio

from app.entrypoints.runtime import configure_logging, validate_runtime
from app.workers.scraper_odoo_delivery import run_forever


def main() -> None:
    configure_logging()
    validate_runtime("middleware-scraper-odoo-delivery")
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()

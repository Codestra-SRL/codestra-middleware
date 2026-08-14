"""Fail-closed JetStream maximum-delivery advisory worker."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import ssl

import nats

from app.entrypoints.runtime import configure_logging, validate_runtime
from app.eventing.jetstream import forward_max_delivery_advisory, read_nats_url

logger = logging.getLogger("codestra.jetstream-dlq")
ADVISORY_SUBJECT = "$JS.EVENT.ADVISORY.CONSUMER.MAX_DELIVERIES.>"


def _enabled() -> bool:
    return os.getenv("JETSTREAM_DLQ_WORKER_ENABLED", "false").lower() == "true"


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=os.environ["NATS_CA_FILE"])
    context.load_cert_chain(
        os.environ["NATS_CLIENT_CERT_FILE"], os.environ["NATS_CLIENT_KEY_FILE"]
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


async def run() -> None:
    configure_logging()
    validate_runtime("middleware-jetstream-dlq-worker")
    if not _enabled():
        raise RuntimeError("JetStream DLQ worker is disabled")

    connection = await nats.connect(
        servers=[read_nats_url(os.environ["NATS_URL_FILE"])],
        tls=_tls_context(),
        name="middleware-jetstream-dlq-worker",
        connect_timeout=5,
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
    )
    jetstream = connection.jetstream()

    async def handler(message) -> None:
        try:
            result = await forward_max_delivery_advisory(jetstream, message.data)
            logger.info("maximum-delivery advisory handled", extra={"result": result})
        except Exception:
            logger.exception("maximum-delivery advisory rejected")

    subscription = await connection.subscribe(ADVISORY_SUBJECT, cb=handler)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, stopped.set)
    try:
        await stopped.wait()
    finally:
        await subscription.unsubscribe()
        await connection.drain()


if __name__ == "__main__":
    asyncio.run(run())

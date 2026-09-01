from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from .api import build_app
from .contracts import seed_control_plane
from .models import Base, Notification, Outbox, Status, TemplateVersion
from .metrics import dead_letter_count, oldest_outbox_age, outbox_depth, retry_count
from .security import TokenValidator
from .templates import TEMPLATES
from .worker import Worker

def database_url() -> str:
    if value := os.getenv("BEYVRA_EMAIL_DATABASE_URL", ""):
        return value
    return Path(os.environ["BEYVRA_EMAIL_DATABASE_URL_FILE"]).read_text(encoding="utf-8").strip()


engine = create_engine(database_url(), pool_pre_ping=True)
Sessions = sessionmaker(engine, expire_on_commit=False)
validator = TokenValidator(os.environ["BEYVRA_EMAIL_ISSUER"], os.getenv("BEYVRA_EMAIL_AUDIENCE", "codestra-email"), os.environ["BEYVRA_EMAIL_JWKS_URL"])
app = build_app(Sessions, validator)


def seed_templates() -> None:
    with Sessions() as db:
        seed_control_plane(db)
        for category, names in TEMPLATES.items():
            for name in names:
                if not db.get(TemplateVersion, (name, 1, "en")):
                    db.add(TemplateVersion(template_id=name, version=1, locale="en", category=category,
                                           subject="Beyvra notification", text_body="{{ action }}",
                                           html_body="<p>{{ action }}</p><p>Access sensitive actions only through the authenticated Beyvra application.</p>",
                                           required_variables=["action"], active=True))
        db.commit()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    seed_templates()


@app.get("/metrics")
def metrics() -> Response:
    with Sessions() as db:
        rows = db.scalars(select(Outbox).where(Outbox.status == "QUEUED")).all()
        outbox_depth.set(len(rows))
        oldest_outbox_age.set(max((time.time() - row.created_at.timestamp() for row in rows), default=0))
        retry_count.set(sum(row.attempt_count for row in rows))
        dead_letter_count.set(db.scalar(select(func.count()).select_from(Notification).where(Notification.status == Status.DEAD_LETTER)) or 0)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def worker_main() -> None:
    if os.getenv("LIVE_EMAIL_DELIVERY", "false").lower() != "true":
        raise RuntimeError("live_email_delivery_disabled")
    Base.metadata.create_all(engine)
    seed_templates()
    worker = Worker(Sessions, os.getenv("HOSTNAME", socket.gethostname()))
    while True:
        claimed = worker.claim()
        for notification_id in claimed:
            worker.deliver(notification_id)
        time.sleep(1 if claimed else 5)

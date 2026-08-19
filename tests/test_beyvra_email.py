from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.email.api import build_app
from app.email.models import Base, DeadLetter, Notification, Outbox, Status, Suppression, TemplateVersion
from app.email.security import AuthorizationError, Principal
from app.email.service import create_notification, record_failure
from app.email.templates import SENDERS, TEMPLATE_CATEGORY, render


class Validator:
    def validate(self, token: str, scope: str) -> Principal:
        if token == "expired":
            raise AuthorizationError("invalid_token")
        scopes = {"email.send", "email.read", "email.retry"} if token == "valid" else {"email.read"}
        if scope not in scopes:
            raise AuthorizationError("insufficient_scope")
        return Principal("beyvra-email-production", frozenset(scopes), "beyvra")


@pytest.fixture()
def sessions():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        for template_id, category in TEMPLATE_CATEGORY.items():
            db.add(TemplateVersion(template_id=template_id, version=1, locale="en", category=category,
                                   subject="Beyvra {{ action }}", text_body="Action: {{ action }}",
                                   html_body="<p>Action: {{ action }}</p>", required_variables=["action"], active=True))
        db.commit()
    return factory


def payload(**changes):
    value = {"event_id": "event-1", "correlation_id": "correlation-1", "idempotency_key": "idem-1",
             "user_id": "user-1", "account_id": "account-1", "template_id": "new_login", "template_version": 1,
             "recipient": "user@example.test", "event_type": "security.new_login", "category": "SECURITY",
             "locale": "en", "parameters": {"action": "New login"}}
    value.update(changes)
    return value


def test_template_catalog_and_safe_rendering():
    assert len(TEMPLATE_CATEGORY) == 41
    assert set(SENDERS) == {"ACCOUNT", "SECURITY", "TRADING", "FUNDS", "STATEMENTS", "SUPPORT", "SYSTEM"}
    rendered = render("{{ value }}", "{{ value }}", "<b>{{ value }}</b>", {"value": "<script>"}, ["value"])
    assert rendered.subject == "<script>" and "&lt;script&gt;" in rendered.html
    with pytest.raises(ValueError, match="unknown_template_variables"):
        render("x", "x", "x", {"extra": "x"}, [])


def test_create_is_idempotent_tenant_scoped_and_server_selects_sender(sessions):
    with sessions() as db:
        first, duplicate = create_notification(db, "beyvra", payload())
        second, duplicate_again = create_notification(db, "beyvra", payload())
        assert not duplicate and duplicate_again and first.notification_id == second.notification_id
        assert first.sender == "security@beyvra.com" and first.status == Status.QUEUED
        assert db.get(Outbox, first.notification_id)
    with sessions() as db:
        other, _ = create_notification(db, "other-tenant", payload())
        assert other.notification_id != first.notification_id


def test_idempotency_conflict_and_suppression(sessions):
    with sessions() as db:
        first, _ = create_notification(db, "beyvra", payload())
        with pytest.raises(ValueError, match="idempotency_conflict"):
            create_notification(db, "beyvra", payload(recipient="other@example.test"))
        db.add(Suppression(tenant_id="beyvra", recipient_hash=first.recipient_hash, reason="hard_bounce"))
        db.commit()
        blocked, _ = create_notification(db, "beyvra", payload(event_id="event-2", idempotency_key="idem-2"))
        assert blocked.status == Status.SUPPRESSED and db.get(Outbox, blocked.notification_id) is None


def test_bounded_retry_and_dead_letter(sessions):
    with sessions() as db:
        row, _ = create_notification(db, "beyvra", payload())
        outbox = db.get(Outbox, row.notification_id)
        for _ in range(5):
            record_failure(db, row, outbox, "NETWORK_FAILURE", "connection refused")
        assert row.status == Status.DEAD_LETTER and outbox.status == "DEAD_LETTER"
        dead = db.get(DeadLetter, row.notification_id)
        assert dead.attempt_count == 5 and dead.error_digest != hashlib.sha256(b"").hexdigest()


def test_auth_scope_tenant_isolation_and_webhook_replay(monkeypatch, sessions, tmp_path):
    secret, token = tmp_path / "webhook", tmp_path / "token"
    secret.write_text("webhook-test-secret", encoding="utf-8")
    token.write_text("webhook-test-token", encoding="utf-8")
    monkeypatch.setenv("POSTAL_WEBHOOK_SECRET_FILE", str(secret))
    monkeypatch.setenv("POSTAL_WEBHOOK_TOKEN_FILE", str(token))
    client = TestClient(build_app(sessions, Validator()))
    assert client.post("/v1/email/messages", json=payload()).status_code == 401
    assert client.post("/v1/email/messages", headers={"Authorization": "Bearer read-only"}, json=payload()).status_code == 403
    created = client.post("/v1/email/messages", headers={"Authorization": "Bearer valid"}, json=payload())
    assert created.status_code == 202
    notification_id = created.json()["notification_id"]
    with sessions() as db:
        row = db.get(Notification, notification_id)
        row.provider_message_id = "postal-1"
        row.status = Status.SUBMITTED
        db.commit()
    value = {"provider_message_id": "postal-1", "status": "delivered", "occurred_at": datetime.now(timezone.utc).isoformat(), "event_type": "MessageDelivery"}
    raw, stamp, event_id = json.dumps(value, separators=(",", ":")).encode(), str(int(time.time())), "postal-event-1"
    signature = hmac.new(b"webhook-test-secret", stamp.encode() + b"\n" + event_id.encode() + b"\n" + raw, hashlib.sha256).hexdigest()
    headers = {"X-Klyrow-Timestamp": stamp, "X-Klyrow-Event-Id": event_id, "X-Klyrow-Signature": "sha256=" + signature,
               "Authorization": "Bearer webhook-test-token", "Content-Type": "application/json"}
    accepted = client.post("/v1/webhooks/postal-native", content=raw, headers=headers)
    assert accepted.status_code == 202
    assert client.post("/v1/webhooks/postal-native", content=raw, headers=headers).status_code == 409
    with sessions() as db:
        assert db.get(Notification, notification_id).status == Status.DELIVERED

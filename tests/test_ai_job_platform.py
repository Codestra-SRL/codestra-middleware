import asyncio
import hashlib
import hmac
import ipaddress
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.internal import ai_jobs as worker_api
from app.api.v1 import ai_console
from app.core import ai_jobs
from app.core.config import settings

SECRET = b"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_worker_contract_has_one_canonical_auth_and_no_memory_replay_store():
    source = (Path(__file__).resolve().parents[1] / "app/api/internal/ai_jobs.py").read_text()
    caddy = (Path(__file__).resolve().parents[1]
             / "deploy/qwen-auth-verifier/Caddyfile.production.snippet").read_text()
    assert "_nonces: dict" not in source
    assert "ai_service_nonces" in source
    assert 'request.method.upper(), request.url.path, service_id' in source
    for header in ("X-Service-ID", "X-HMAC-Key-ID", "X-Timestamp", "X-Nonce",
                   "X-Body-SHA256", "X-Signature"):
        assert header in source
    for spoofable in ("X-Client-Certificate-Serial", "X-Client-SPIFFE-ID",
                      "X-Service-Scopes"):
        assert f"header_up -{spoofable}" in caddy
        assert spoofable not in source


def test_nonce_migration_is_atomic_durable_and_reversible():
    migration = (Path(__file__).resolve().parents[1]
                 / "migrations/versions/0030_ai_job_platform.py").read_text()
    assert "CREATE TABLE ai_service_nonces" in migration
    assert "PRIMARY KEY(service_id, nonce_digest)" in migration
    assert "nonce_digest char(64)" in migration
    assert "expires_at timestamptz NOT NULL" in migration
    assert "DROP TABLE ai_service_nonces" in migration


def worker_headers(method: str, path: str, body: bytes, certificate: bytes,
                   nonce: str | None = None, timestamp: str | None = None,
                   service_id: str = "qwen-ai-01", key_id: str = "qwen-ai-01-hmac-20260804-01"):
    timestamp = timestamp or str(int(time.time()))
    nonce = nonce or uuid4().hex
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((method.upper(), path, service_id, timestamp, nonce, digest))
    return {
        "X-Service-ID": service_id, "X-HMAC-Key-ID": key_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce, "X-Signature": hmac.new(SECRET, canonical.encode(), hashlib.sha256).hexdigest(),
        "X-Body-SHA256": digest,
        "X-Codestra-Client-Certificate": quote(certificate.decode(), safe=""),
        "X-Codestra-Source-IP": "10.40.0.4",
        "X-Correlation-ID": f"corr-{nonce}",
        "X-Client-Certificate-Serial": "attacker-controlled",
        "X-Client-SPIFFE-ID": "spiffe://attacker.invalid/service/root",
        "X-Service-Scopes": "root admin write",
    }


def certificates(tmp_path):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(1)
          .not_valid_before(now - timedelta(minutes=1))
          .not_valid_after(now + timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "qwen-ai-01")])
    def issue(*, serial=12289,
              spiffe="spiffe://codestra.internal/service/qwen-ai-01",
              digital_signature=True, client_auth=True, signer=ca_key, issuer=ca_name):
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        builder = (x509.CertificateBuilder().subject_name(leaf_name).issuer_name(issuer)
            .public_key(leaf_key.public_key()).serial_number(serial)
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("10.40.0.4")),
                x509.UniformResourceIdentifier(spiffe)]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=digital_signature, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True))
        if client_auth:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
        return builder.sign(signer, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Other CA")])
    ca_path = tmp_path / "ca.pem"
    secret_path = tmp_path / "hmac"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    secret_path.write_bytes(SECRET)
    return ca_path, secret_path, {
        "valid": issue(),
        "wrong_serial": issue(serial=12290),
        "wrong_spiffe": issue(spiffe="spiffe://codestra.internal/service/wrong"),
        "no_client_auth": issue(client_auth=False),
        "no_digital_signature": issue(digital_signature=False),
        "unapproved_ca": issue(signer=other_key, issuer=other_name),
    }


@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required")
@pytest.mark.asyncio
async def test_durable_job_lifecycle_tenant_stream_cancel_and_recovery(tmp_path):
    organization_id, workspace_id = uuid4(), uuid4()
    other_organization = uuid4()
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    ca_path, secret_path, certificate_set = certificates(tmp_path)
    client_certificate = certificate_set["valid"]
    settings.ai_hmac_secret_file = str(secret_path)
    settings.ai_worker_client_ca_file = str(ca_path)
    settings.ai_worker_source_cidrs = "10.40.0.4/32"
    settings.ai_worker_trusted_proxy_cidr = "10.250.241.2/32"
    settings.ai_worker_certificate_serial = "12289"

    auth_app = FastAPI()
    auth_app.include_router(worker_api.router)

    async def auth_session():
        async with session_factory() as session:
            yield session

    auth_app.dependency_overrides[worker_api.get_session] = auth_session
    auth_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_app, client=("10.250.241.2", 443)),
        base_url="http://test",
    )
    verify_path = "/internal/api/v1/ai/auth/verify"
    valid = worker_headers("POST", verify_path, b"", client_certificate)
    accepted = await auth_client.post(verify_path, headers=valid)
    assert accepted.status_code == 200
    assert accepted.json()["scope"] == "ai.auth.verify/read-only"
    assert (await auth_client.post(verify_path, headers=valid)).status_code == 409
    race = worker_headers("POST", verify_path, b"", client_certificate)
    raced = await asyncio.gather(
        auth_client.post(verify_path, headers=race),
        auth_client.post(verify_path, headers=race),
    )
    assert sorted(item.status_code for item in raced) == [200, 409]
    bad_signature = worker_headers("POST", verify_path, b"", client_certificate)
    bad_signature["X-Signature"] = "0" * 64
    assert (await auth_client.post(verify_path, headers=bad_signature)).status_code == 401
    expired = worker_headers("POST", verify_path, b"", client_certificate,
        timestamp=str(int(time.time()) - 301))
    assert (await auth_client.post(verify_path, headers=expired)).status_code == 401
    future = worker_headers("POST", verify_path, b"", client_certificate,
        timestamp=str(int(time.time()) + 301))
    assert (await auth_client.post(verify_path, headers=future)).status_code == 401
    wrong_service = worker_headers("POST", verify_path, b"", client_certificate,
        service_id="wrong-service")
    assert (await auth_client.post(verify_path, headers=wrong_service)).status_code == 403
    wrong_key = worker_headers("POST", verify_path, b"", client_certificate,
        key_id="wrong-key")
    assert (await auth_client.post(verify_path, headers=wrong_key)).status_code == 403
    missing_certificate = worker_headers("POST", verify_path, b"", client_certificate)
    del missing_certificate["X-Codestra-Client-Certificate"]
    assert (await auth_client.post(verify_path, headers=missing_certificate)).status_code == 422
    wrong_source = worker_headers("POST", verify_path, b"", client_certificate)
    wrong_source["X-Codestra-Source-IP"] = "10.40.0.5"
    assert (await auth_client.post(verify_path, headers=wrong_source)).status_code == 404
    for certificate_name in (
        "wrong_serial", "wrong_spiffe", "no_client_auth",
        "no_digital_signature", "unapproved_ca",
    ):
        rejected = worker_headers("POST", verify_path, b"", certificate_set[certificate_name])
        assert (await auth_client.post(verify_path, headers=rejected)).status_code == 401
    modified = worker_headers("POST", verify_path, b"", client_certificate)
    assert (await auth_client.post(verify_path, content=b"modified", headers=modified)).status_code == 401
    await auth_client.aclose()
    async with session_factory() as db:
        await db.execute(text("""TRUNCATE ai_audit_events, ai_worker_heartbeats,
            ai_job_attempts, ai_job_chunks, ai_generation_jobs, ai_messages,
            ai_conversations CASCADE"""))
        await db.commit()
        conversation = await ai_jobs.create_conversation(
            db, organization_id, workspace_id, "synthetic-user", "Synthetic", "corr-create"
        )
        job = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="example.invalid prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0001",
            correlation_id="corr-job", max_attempts=2,
        )
        replay = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="example.invalid prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0001",
            correlation_id="corr-replay", max_attempts=2,
        )
        assert replay["job_id"] == job["job_id"] and replay["idempotent_replay"]
        claimed = await ai_jobs.claim(db, "synthetic-worker", 30, "corr-claim")
        assert claimed and claimed["id"] == job["job_id"]
        job_id = claimed["id"]
        assert await ai_jobs.append_chunk(db, job_id, "synthetic-worker",
            claimed["fencing_token"], 0, "synthetic output", 1024)
        assert not await ai_jobs.append_chunk(db, job_id, "synthetic-worker",
            claimed["fencing_token"], 0, "synthetic output", 1024)
        assert await ai_jobs.finish(db, job_id, "synthetic-worker", claimed["fencing_token"],
            failed=False, error_code=None, retryable=False, correlation_id="corr-complete") == "completed"
        with pytest.raises(PermissionError):
            await ai_jobs.heartbeat(db, job_id, "synthetic-worker", claimed["fencing_token"], 30)

        second = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="second synthetic prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0002",
            correlation_id="corr-second", max_attempts=1,
        )
        second_claim = await ai_jobs.claim(db, "synthetic-worker", 30, "corr-second-claim")
        await db.execute(text("UPDATE ai_generation_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=:id"),
                         {"id": second["job_id"]})
        await db.commit()
        recovered = await ai_jobs.recover_expired(db)
        assert recovered == {"retried": 0, "dead_lettered": 1}
        assert second_claim["attempt_count"] == 1

        third = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="cancel synthetic prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0003",
            correlation_id="corr-third", max_attempts=2,
        )

    app = FastAPI()
    app.include_router(ai_console.router)
    tenant_state = {"organization_id": organization_id}

    def browser_tenant():
        return ai_console.Tenant(
            tenant_state["organization_id"], workspace_id,
            "synthetic-user", frozenset({"codestra_ai_user"}),
        )

    async def isolated_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[ai_console.get_session] = isolated_session
    app.dependency_overrides[ai_console.tenant] = browser_tenant
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    base_headers = {"Authorization": "Bearer synthetic", "X-Organization-ID": str(organization_id),
                    "X-Workspace-ID": str(workspace_id), "X-User-ID": "synthetic-user",
                    "X-Correlation-ID": "corr-cancel"}
    cancel = await client.post(f"/api/v1/ai/jobs/{third['job_id']}/cancel", headers=base_headers)
    assert cancel.status_code == 202 and cancel.json()["cancel_requested"]
    stream = await client.get(f"/api/v1/ai/jobs/{job_id}/stream", headers=base_headers)
    assert stream.status_code == 200
    assert "synthetic output" in stream.text and '"state": "completed"' in stream.text
    tenant_state["organization_id"] = other_organization
    isolated = await client.get(f"/api/v1/ai/jobs/{job_id}/stream", headers=base_headers)
    assert '"code":"not_found"' in isolated.text
    await client.aclose()
    await engine.dispose()

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import httpx
import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.internal import ai_jobs as worker_api
from app.api.v1 import ai_console
from app import main as middleware_main
from app.core import ai_jobs
from app.core.config import settings

SECRET = b"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_worker_contract_has_one_canonical_auth_and_no_memory_replay_store():
    source = (
        Path(__file__).resolve().parents[1] / "app/api/internal/ai_jobs.py"
    ).read_text()
    caddy = (
        Path(__file__).resolve().parents[1]
        / "deploy/qwen-worker/Caddyfile.private-worker-api.snippet"
    ).read_text()
    assert "_nonces: dict" not in source
    assert "ai_service_nonces" in source
    assert "canonical_signing_string_v2(" in source
    for signed_field in ("request_id", "correlation_id", "worker_id"):
        assert signed_field in source
    assert 'signature_version != "v2"' in source
    for header in (
        "X-Service-ID",
        "X-HMAC-Key-ID",
        "X-Timestamp",
        "X-Nonce",
        "X-Body-SHA256",
        "X-Signature",
    ):
        assert header in source
    for spoofable in (
        "X-Client-Certificate-Serial",
        "X-Client-SPIFFE-ID",
        "X-Service-Scopes",
    ):
        assert f"header_up -{spoofable}" in caddy
        assert spoofable not in source


def test_ai_router_enforces_authentication_and_outer_guard_fails_closed():
    assert ai_console.router.dependencies
    assert any(
        item.dependency is ai_console.tenant for item in ai_console.router.dependencies
    )
    assert not hasattr(middleware_main, "SELF_AUTHENTICATED_PREFIXES")
    with TestClient(middleware_main.app) as client:
        current = client.post("/api/v1/ai/conversations", json={"title": "x"})
        commands = client.post("/api/v1/ai/commands", json={})
        future = client.get("/api/v1/ai/_future-auth-regression")
    assert current.status_code in {401, 422}
    assert commands.status_code in {401, 422}
    assert future.status_code in {401, 503}


def test_ai_tenant_uses_real_rs256_validation(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    organization_id, workspace_id = uuid4(), uuid4()
    now = int(time.time())

    class SigningKey:
        key = private_key.public_key()

    class JWKClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return SigningKey()

    monkeypatch.setattr(jwt, "PyJWKClient", JWKClient)
    monkeypatch.setattr(
        settings,
        "keycloak_issuer",
        "https://identity.example.invalid/realms/codestra",
    )
    monkeypatch.setattr(settings, "keycloak_audience", "codestra-ai-console")
    monkeypatch.setattr(
        settings, "keycloak_jwks_url", "https://identity.example.invalid/jwks"
    )
    monkeypatch.setattr(settings, "keycloak_authorized_parties", "codestra-ai-console")
    ai_console._validator.cache_clear()
    token = jwt.encode(
        {
            "iss": settings.keycloak_issuer,
            "aud": settings.keycloak_audience,
            "azp": "codestra-ai-console",
            "sub": "synthetic-user",
            "iat": now,
            "exp": now + 300,
            "organization_id": str(organization_id),
            "workspace_id": str(workspace_id),
            "realm_access": {"roles": ["codestra_ai_user"]},
        },
        private_key,
        algorithm="RS256",
    )
    subject = ai_console.tenant(f"Bearer {token}")
    assert subject.organization_id == organization_id
    assert subject.workspace_id == workspace_id
    assert subject.user_id == "synthetic-user"
    with pytest.raises(HTTPException) as denied:
        ai_console.tenant("Bearer invalid")
    assert denied.value.status_code == 401
    ai_console._validator.cache_clear()


def test_nonce_migration_is_atomic_durable_and_reversible():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/0030_ai_job_platform.py"
    ).read_text()
    assert "CREATE TABLE ai_service_nonces" in migration
    assert "PRIMARY KEY(service_id, nonce_digest)" in migration
    assert "nonce_digest char(64)" in migration
    assert "expires_at timestamptz NOT NULL" in migration
    assert "DROP TABLE ai_service_nonces" in migration


def worker_headers(
    method: str,
    path: str,
    body: bytes,
    certificate: bytes,
    nonce: str | None = None,
    timestamp: str | None = None,
    service_id: str = "qwen-ai-01",
    key_id: str = "qwen-ai-01-hmac-20260804-01",
    tenant_id: str = "00000000-0000-4000-8000-000000000001",
    workspace_id: str = "00000000-0000-4000-8000-000000000002",
):
    timestamp = timestamp or str(int(time.time()))
    nonce = nonce or uuid4().hex
    digest = hashlib.sha256(body).hexdigest()
    request_id = f"request-{nonce}"
    correlation_id = f"corr-{nonce}"
    worker_id = "qwen-ai-01-worker"
    canonical = "\n".join(
        (
            method.upper(),
            path,
            timestamp,
            nonce,
            digest,
            request_id,
            correlation_id,
            worker_id,
        )
    )
    return {
        "X-Service-ID": service_id,
        "X-HMAC-Key-ID": key_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": hmac.new(SECRET, canonical.encode(), hashlib.sha256).hexdigest(),
        "X-Body-SHA256": digest,
        "X-Codestra-Client-Certificate-DER": base64.b64encode(
            x509.load_pem_x509_certificate(certificate).public_bytes(
                serialization.Encoding.DER
            )
        ).decode("ascii"),
        "X-Codestra-Source-IP": "10.40.0.4",
        "X-Correlation-ID": correlation_id,
        "X-Request-ID": request_id,
        "X-Worker-ID": worker_id,
        "X-Signature-Version": "v2",
        "X-Tenant-ID": tenant_id,
        "X-Workspace-ID": workspace_id,
        "X-Client-Certificate-Serial": "attacker-controlled",
        "X-Client-SPIFFE-ID": "spiffe://attacker.invalid/service/root",
        "X-Service-Scopes": "root admin write",
    }


def certificates(tmp_path):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "qwen-ai-01")])

    def issue(
        *,
        serial=12289,
        ip_san="10.40.0.4",
        spiffe="spiffe://codestra.internal/service/qwen-ai-01",
        digital_signature=True,
        client_auth=True,
        signer=ca_key,
        issuer=ca_name,
    ):
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        builder = (
            x509.CertificateBuilder()
            .subject_name(leaf_name)
            .issuer_name(issuer)
            .public_key(leaf_key.public_key())
            .serial_number(serial)
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.IPAddress(ipaddress.ip_address(ip_san)),
                        x509.UniformResourceIdentifier(spiffe),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=digital_signature,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
        )
        if client_auth:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True
            )
        return builder.sign(signer, hashes.SHA256()).public_bytes(
            serialization.Encoding.PEM
        )

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Other CA")])
    ca_path = tmp_path / "ca.pem"
    secret_path = tmp_path / "hmac"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    secret_path.write_bytes(SECRET)
    return (
        ca_path,
        secret_path,
        {
            "valid": issue(),
            "wrong_serial": issue(serial=12290),
            "wrong_spiffe": issue(spiffe="spiffe://codestra.internal/service/wrong"),
            "wrong_ip": issue(ip_san="10.40.0.5"),
            "no_client_auth": issue(client_auth=False),
            "no_digital_signature": issue(digital_signature=False),
            "unapproved_ca": issue(signer=other_key, issuer=other_name),
        },
    )


@pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required"
)
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
    settings.ai_worker_service_id = "qwen-ai-01"
    settings.ai_worker_hmac_key_id = "qwen-ai-01-hmac-20260804-01"
    settings.ai_worker_spiffe_id = "spiffe://codestra.internal/service/qwen-ai-01"

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
    restarted_app = FastAPI()
    restarted_app.include_router(worker_api.router)
    restarted_app.dependency_overrides[worker_api.get_session] = auth_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted_app, client=("10.250.241.2", 443)),
        base_url="http://test",
    ) as restarted_client:
        assert (
            await restarted_client.post(verify_path, headers=valid)
        ).status_code == 409
    race = worker_headers("POST", verify_path, b"", client_certificate)
    raced = await asyncio.gather(
        auth_client.post(verify_path, headers=race),
        auth_client.post(verify_path, headers=race),
    )
    assert sorted(item.status_code for item in raced) == [200, 409]
    bad_signature = worker_headers("POST", verify_path, b"", client_certificate)
    bad_signature["X-Signature"] = "0" * 64
    assert (
        await auth_client.post(verify_path, headers=bad_signature)
    ).status_code == 401
    expired = worker_headers(
        "POST",
        verify_path,
        b"",
        client_certificate,
        timestamp=str(int(time.time()) - 301),
    )
    assert (await auth_client.post(verify_path, headers=expired)).status_code == 401
    future = worker_headers(
        "POST",
        verify_path,
        b"",
        client_certificate,
        timestamp=str(int(time.time()) + 301),
    )
    assert (await auth_client.post(verify_path, headers=future)).status_code == 401
    wrong_service = worker_headers(
        "POST", verify_path, b"", client_certificate, service_id="wrong-service"
    )
    assert (
        await auth_client.post(verify_path, headers=wrong_service)
    ).status_code == 401
    wrong_key = worker_headers(
        "POST", verify_path, b"", client_certificate, key_id="wrong-key"
    )
    assert (await auth_client.post(verify_path, headers=wrong_key)).status_code == 401
    wrong_worker = worker_headers("POST", verify_path, b"", client_certificate)
    wrong_worker["X-Worker-ID"] = "wrong-worker"
    assert (
        await auth_client.post(verify_path, headers=wrong_worker)
    ).status_code == 401
    missing_certificate = worker_headers("POST", verify_path, b"", client_certificate)
    del missing_certificate["X-Codestra-Client-Certificate-DER"]
    assert (
        await auth_client.post(verify_path, headers=missing_certificate)
    ).status_code == 422
    malformed_certificate = worker_headers("POST", verify_path, b"", client_certificate)
    malformed_certificate["X-Codestra-Client-Certificate-DER"] = "not-base64%%%"
    assert (
        await auth_client.post(verify_path, headers=malformed_certificate)
    ).status_code == 401
    wrong_source = worker_headers("POST", verify_path, b"", client_certificate)
    wrong_source["X-Codestra-Source-IP"] = "10.40.0.5"
    assert (
        await auth_client.post(verify_path, headers=wrong_source)
    ).status_code == 404
    for certificate_name in (
        "wrong_serial",
        "wrong_spiffe",
        "wrong_ip",
        "no_client_auth",
        "no_digital_signature",
        "unapproved_ca",
    ):
        rejected = worker_headers(
            "POST", verify_path, b"", certificate_set[certificate_name]
        )
        assert (
            await auth_client.post(verify_path, headers=rejected)
        ).status_code == 401
    modified = worker_headers("POST", verify_path, b"", client_certificate)
    assert (
        await auth_client.post(verify_path, content=b"modified", headers=modified)
    ).status_code == 401
    await auth_client.aclose()
    async with session_factory() as db:
        await db.execute(
            text("""TRUNCATE ai_audit_events, ai_worker_heartbeats,
            ai_job_attempts, ai_job_chunks, ai_generation_jobs, ai_messages,
            ai_conversations CASCADE""")
        )
        await db.commit()
        conversation = await ai_jobs.create_conversation(
            db,
            organization_id,
            workspace_id,
            "synthetic-user",
            "Synthetic",
            "corr-create",
        )
        job = await ai_jobs.create_message_job(
            db,
            conversation_id=conversation["conversation_id"],
            organization_id=organization_id,
            workspace_id=workspace_id,
            user_id="synthetic-user",
            content="example.invalid prompt",
            task_type="chat",
            project_key=None,
            idempotency_key="fixture-key-0001",
            correlation_id="corr-job",
            max_attempts=2,
        )
        replay = await ai_jobs.create_message_job(
            db,
            conversation_id=conversation["conversation_id"],
            organization_id=organization_id,
            workspace_id=workspace_id,
            user_id="synthetic-user",
            content="example.invalid prompt",
            task_type="chat",
            project_key=None,
            idempotency_key="fixture-key-0001",
            correlation_id="corr-replay",
            max_attempts=2,
        )
        assert replay["job_id"] == job["job_id"] and replay["idempotent_replay"]
        claimed = await ai_jobs.claim(db, "synthetic-worker", 30, "corr-claim")
        assert claimed and claimed["id"] == job["job_id"]
        job_id = claimed["id"]
        assert await ai_jobs.append_chunk(
            db,
            job_id,
            "synthetic-worker",
            claimed["fencing_token"],
            0,
            "synthetic output",
            1024,
        )
        assert not await ai_jobs.append_chunk(
            db,
            job_id,
            "synthetic-worker",
            claimed["fencing_token"],
            0,
            "synthetic output",
            1024,
        )
        assert (
            await ai_jobs.finish(
                db,
                job_id,
                "synthetic-worker",
                claimed["fencing_token"],
                failed=False,
                error_code=None,
                retryable=False,
                correlation_id="corr-complete",
            )
            == "completed"
        )
        with pytest.raises(PermissionError):
            await ai_jobs.heartbeat(
                db,
                job_id,
                "synthetic-worker",
                claimed["fencing_token"],
                30,
                service_id="qwen-ai-01",
                certificate_serial="12289",
                spiffe_id="spiffe://codestra.internal/service/qwen-ai-01",
            )

        second = await ai_jobs.create_message_job(
            db,
            conversation_id=conversation["conversation_id"],
            organization_id=organization_id,
            workspace_id=workspace_id,
            user_id="synthetic-user",
            content="second synthetic prompt",
            task_type="chat",
            project_key=None,
            idempotency_key="fixture-key-0002",
            correlation_id="corr-second",
            max_attempts=1,
        )
        second_claim = await ai_jobs.claim(
            db, "synthetic-worker", 30, "corr-second-claim"
        )
        await db.execute(
            text(
                "UPDATE ai_generation_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=:id"
            ),
            {"id": second["job_id"]},
        )
        await db.commit()
        recovered = await ai_jobs.recover_expired(db)
        assert recovered == {"retried": 0, "dead_lettered": 1}
        assert second_claim["attempt_count"] == 1

        third = await ai_jobs.create_message_job(
            db,
            conversation_id=conversation["conversation_id"],
            organization_id=organization_id,
            workspace_id=workspace_id,
            user_id="synthetic-user",
            content="cancel synthetic prompt",
            task_type="chat",
            project_key=None,
            idempotency_key="fixture-key-0003",
            correlation_id="corr-third",
            max_attempts=2,
        )

    app = FastAPI()
    app.include_router(ai_console.router)
    tenant_state = {"organization_id": organization_id}

    def browser_tenant():
        return ai_console.Tenant(
            tenant_state["organization_id"],
            workspace_id,
            "synthetic-user",
            frozenset({"codestra_ai_user"}),
        )

    async def isolated_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[ai_console.get_session] = isolated_session
    app.dependency_overrides[ai_console.tenant] = browser_tenant
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    base_headers = {
        "Authorization": "Bearer synthetic",
        "X-Organization-ID": str(organization_id),
        "X-Workspace-ID": str(workspace_id),
        "X-User-ID": "synthetic-user",
        "X-Correlation-ID": "corr-cancel",
    }
    cancel = await client.post(
        f"/api/v1/ai/jobs/{third['job_id']}/cancel", headers=base_headers
    )
    assert cancel.status_code == 202 and cancel.json()["cancel_requested"]
    stream = await client.get(f"/api/v1/ai/jobs/{job_id}/stream", headers=base_headers)
    assert stream.status_code == 200
    assert "synthetic output" in stream.text and '"state": "completed"' in stream.text
    tenant_state["organization_id"] = other_organization
    isolated = await client.get(
        f"/api/v1/ai/jobs/{job_id}/stream", headers=base_headers
    )
    assert '"code":"not_found"' in isolated.text
    await client.aclose()
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="disposable PostgreSQL required",
)
@pytest.mark.asyncio
async def test_concurrent_idempotency_and_claim_are_atomic():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    organization_id, workspace_id = uuid4(), uuid4()
    async with session_factory() as db:
        await db.execute(
            text(
                """TRUNCATE ai_audit_events, ai_worker_heartbeats,
                ai_job_attempts, ai_job_chunks, ai_generation_jobs,
                ai_messages, ai_conversations CASCADE"""
            )
        )
        await db.commit()
        conversation = await ai_jobs.create_conversation(
            db,
            organization_id,
            workspace_id,
            "synthetic-user",
            "Concurrent fixture",
            "corr-concurrent-conversation",
        )

    async def submit(correlation_id: str):
        async with session_factory() as db:
            return await ai_jobs.create_message_job(
                db,
                conversation_id=conversation["conversation_id"],
                organization_id=organization_id,
                workspace_id=workspace_id,
                user_id="synthetic-user",
                content="example.invalid concurrent request",
                task_type="chat",
                project_key=None,
                idempotency_key="fixture-concurrent-idempotency-key",
                correlation_id=correlation_id,
                max_attempts=2,
            )

    first, second = await asyncio.gather(
        submit("corr-concurrent-first"),
        submit("corr-concurrent-second"),
    )
    assert first["job_id"] == second["job_id"]
    assert sorted([first["idempotent_replay"], second["idempotent_replay"]]) == [
        False,
        True,
    ]

    async def claim(worker_id: str):
        async with session_factory() as db:
            return await ai_jobs.claim(db, worker_id, 30, f"corr-{worker_id}")

    claims = await asyncio.gather(claim("worker-a"), claim("worker-b"))
    assert sum(item is not None for item in claims) == 1
    async with session_factory() as db:
        counts = (
            (
                await db.execute(
                    text(
                        """SELECT
                    (SELECT count(*) FROM ai_messages) AS messages,
                    (SELECT count(*) FROM ai_generation_jobs) AS jobs,
                    (SELECT count(*) FROM ai_job_attempts) AS attempts"""
                    )
                )
            )
            .mappings()
            .one()
        )
    assert dict(counts) == {"messages": 1, "jobs": 1, "attempts": 1}
    await engine.dispose()

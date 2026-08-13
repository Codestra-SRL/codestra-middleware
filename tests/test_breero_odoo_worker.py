from pathlib import Path
import asyncio

import httpx
import pytest

from app.core.config import settings
from app.workers.breero_odoo_delivery import CLAIM, RECOVER, DeliveryError, OdooClient


def configure(monkeypatch, tmp_path: Path):
    key=tmp_path/"odoo-key"
    key.write_text("test-only-key")
    monkeypatch.setattr(settings,"breero_odoo_url","https://odoo.example.test")
    monkeypatch.setattr(settings,"breero_odoo_database","codestra_odoo")
    monkeypatch.setattr(settings,"breero_odoo_username","breero.integration")
    monkeypatch.setattr(settings,"breero_odoo_api_key_file",str(key))
    monkeypatch.setattr(settings,"breero_odoo_ca_file","")


def test_claim_is_concurrent_and_lease_safe():
    sql=str(CLAIM)
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "lease_token" in sql and "lease_expires_at" in sql
    assert "retry_wait" in sql


def test_stale_recovery_is_postgres_authoritative():
    sql=str(RECOVER)
    assert "lease_expires_at < now()" in sql
    assert "STALE_LEASE_RECOVERED" in sql


def test_client_invokes_only_typed_breero_method(monkeypatch,tmp_path):
    configure(monkeypatch,tmp_path)
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={"result":{"event_id":"event-1","odoo_model":"crm.lead","odoo_record_id":42}})
    async def run():
        client=OdooClient()
        await client.http.aclose()
        client.http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ack=await client.deliver({"event_id":"event-1"})
        await client.aclose()
        return ack
    ack=asyncio.run(run())
    rpc=__import__("json").loads(calls[0].content)
    args=rpc["params"]["args"]
    assert args[3:5]==["breero.sync.event","process_breero_event"]
    assert ack["odoo_record_id"]==42


def test_terminal_auth_failure(monkeypatch,tmp_path):
    configure(monkeypatch,tmp_path)
    async def run():
        client=OdooClient()
        await client.http.aclose()
        client.http=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,json={"error":{"data":{"name":"odoo.exceptions.AccessDenied"}}})))
        try:
            await client.deliver({"event_id":"event-1"})
        finally:
            await client.aclose()
    with pytest.raises(DeliveryError) as failure:
        asyncio.run(run())
    assert failure.value.terminal is True

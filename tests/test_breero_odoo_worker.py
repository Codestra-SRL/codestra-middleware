from pathlib import Path

import pytest

from app.core.config import Settings
from app.workers.breero_odoo import DeliveryFailure, RestrictedOdooTransport, ROUTES


def test_worker_is_disabled_and_credentials_are_file_backed():
    value = Settings()
    assert value.breero_odoo_delivery_enabled is False
    assert value.breero_odoo_api_key_file == ""
    source = Path("app/workers/breero_odoo.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "lease_token=:token" in source
    assert '"breero.sync.event"' in source
    assert '"process_breero_event"' in source
    assert "res.users" not in source


def test_four_routes_only():
    assert ROUTES == {
        "BREERO_CUSTOMER_REQUESTS",
        "BREERO_SUPPORT_BUSINESS",
        "BREERO_PROVIDER_RECRUITMENT",
        "BREERO_LEAD_DISPUTES",
    }


@pytest.mark.asyncio
async def test_missing_secret_is_permanent(monkeypatch):
    monkeypatch.setattr(
        "app.workers.breero_odoo.settings.breero_odoo_api_key_file", "/missing"
    )
    with pytest.raises(DeliveryFailure) as caught:
        await RestrictedOdooTransport().deliver({}, "idem")
    assert caught.value.permanent and caught.value.code == "credential_unavailable"


def test_migration_and_entrypoint_are_non_destructive_and_disabled():
    entry = Path("app/entrypoints/breero_odoo_worker.py").read_text()
    assert "if not settings.breero_odoo_delivery_enabled" in entry
    migration = Path("migrations/versions/0044_breero_integration.py").read_text()
    assert "ON DELETE RESTRICT" in migration

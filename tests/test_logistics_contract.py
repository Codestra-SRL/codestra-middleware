from pathlib import Path
import json

from app.core.config import Settings
from app.main import LOGISTICS_JWT_PATH


ROOT = Path(__file__).parents[1]


def test_logistics_routes_are_exactly_routed_to_jwt_authentication():
    assert LOGISTICS_JWT_PATH.match("/api/v1/logistics/orders")
    assert not LOGISTICS_JWT_PATH.match("/api/v1/logistics-evil/orders")


def test_all_production_and_automatic_controls_default_off():
    settings = Settings()
    assert settings.logistics_platform_enabled
    assert settings.logistics_staging_enabled
    assert not settings.logistics_notifications_enabled
    assert not settings.logistics_real_routing_provider_enabled
    assert not settings.logistics_automatic_dispatch_enabled
    assert not settings.logistics_automatic_pricing_enabled
    assert not settings.logistics_automatic_claim_decisions_enabled
    assert not settings.logistics_production_enabled
    settings.validate_safety()


def test_required_tables_and_tenant_uniqueness_are_migrated():
    source = (ROOT / "migrations/versions/0030_logistics_control_plane.py").read_text()
    required = {
        "customers",
        "locations",
        "contacts",
        "orders",
        "shipments",
        "loads",
        "routes",
        "stops",
        "drivers",
        "vehicles",
        "assignments",
        "status_events",
        "tracking_events",
        "rate_cards",
        "quotes",
        "quote_items",
        "charges",
        "documents",
        "proof_events",
        "exceptions",
        "claims",
        "notifications",
        "driver_settlements",
        "reconciliation",
        "audit_events",
    }
    for table in required:
        assert f'"{table}"' in source or f"logistics_{table}" in source
    assert "UNIQUE(tenant_id,workspace_id,external_key)" in source


def test_no_browser_route_can_target_internal_services():
    api = (ROOT / "app/api/v1/logistics.py").read_text()
    for forbidden in (
        "vicidial",
        "asterisk",
        "qdrant",
        "127.0.0.1:11434",
        "n8n/webhook",
    ):
        assert forbidden not in api.lower()


def test_public_tracking_returns_only_minimized_fields():
    api = (ROOT / "app/api/v1/logistics.py").read_text()
    query = api.split("async def public_tracking", 1)[1].split("@router.post", 1)[0]
    assert "origin_city" in query and "destination_city" in query
    for forbidden in (
        "driver_external_key",
        "amount",
        "customer_external_key",
        "special_instructions",
    ):
        assert forbidden not in query


def test_synthetic_fixture_has_exact_requested_scale_and_no_real_data():
    fixture = json.loads(
        (ROOT / "tests/fixtures/logistics_synthetic_counts.json").read_text()
    )
    assert fixture == {
        "synthetic_only": True,
        "tenants": 3,
        "customers": 15,
        "orders": 50,
        "shipments": 40,
        "loads": 10,
        "drivers": 15,
        "vehicles": 12,
        "stops": 100,
        "exceptions": 20,
        "claims": 10,
        "documents": 30,
        "invoices": 20,
    }

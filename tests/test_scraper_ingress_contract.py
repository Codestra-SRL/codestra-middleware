import hashlib
import json
from pathlib import Path

from app.sales.contracts import LeadCandidate


SCHEMA_SHA256 = "27fe4d905420009ba39ec770aca8cdeaf4e354fcc6676745c492d0cfae975c22"


def test_published_scraper_schema_checksum_matches_runtime_contract() -> None:
    encoded = json.dumps(
        LeadCandidate.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    assert hashlib.sha256(encoded).hexdigest() == SCHEMA_SHA256


def test_ingress_contract_is_secret_free_and_fail_closed() -> None:
    contract = Path("docs/sales/SCRAPER_INGRESS_CONTRACT.md").read_text()
    assert SCHEMA_SHA256 in contract
    assert "PENDING_PROTECTED_MAIN_MERGE" in contract
    assert "ZZ_CDX_SCRAPER_CANARY_" in contract
    assert "codestra.scraper-ingress.v1-rc2" in contract
    assert "https://auth.codestra.agency/realms/codestra" in contract
    assert "scraper.events.write" in contract
    assert "scraper-publisher" in contract
    assert "hmac-sha256-v2" in contract
    assert "X-Codestra-Key-ID" in contract
    assert "hmac-sha256-v1" not in contract
    assert "Direct access to Odoo" in contract
    assert "password=" not in contract.lower()


def test_ingress_deployment_overlay_is_disabled_and_credential_free() -> None:
    overlay = Path("deploy/scraper/compose.ingress.yaml").read_text()
    assert "SCRAPER_RESULT_INGEST_ENABLED:-false" in overlay
    assert "codestra-scraper-ingress" in overlay
    assert "scraper.events.write" in overlay
    assert "scraper-publisher" in overlay
    assert "/run/secrets/scraper-ingress/hmac-keys" in overlay
    assert "read_only: true" in overlay
    assert "password" not in overlay.lower()
    assert "client_secret" not in overlay.lower()


def test_scraper_keycloak_client_is_least_privilege_and_not_self_approved() -> None:
    client = json.loads(Path("deploy/scraper/keycloak-service-client.json").read_text())
    assert client["status"] == "ENROLLMENT_REQUIRED"
    assert client["client_id"] == "codestra-scraper-production"
    assert client["service_accounts_enabled"] is True
    assert client["interactive_flows_enabled"] is False
    assert client["direct_access_grants_enabled"] is False
    assert client["public_client"] is False
    assert client["audience"] == "codestra-scraper-ingress"
    assert client["realm_roles"] == ["scraper-publisher"]
    assert client["scopes"] == ["scraper.events.write"]
    assert client["claims"] == {
        "environment": "production",
        "tenant_id": "TENANT-SYNTHETIC",
        "campaigns": ["TEST_SYN"],
    }
    assert set(client) & {"secret", "password", "token", "private_key"} == set()

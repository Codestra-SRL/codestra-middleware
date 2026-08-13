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
    assert "Direct access to Odoo" in contract
    assert "password=" not in contract.lower()

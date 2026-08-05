import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "docs/enterprise-core/legacy-governance-inventory.json"
WAVES = ROOT / "docs/enterprise-core/legacy-governance-waves.json"
RESTIC = ROOT / "scripts/validate_offsite_restic.sh"


def test_inventory_is_complete_and_never_invents_backfill():
    inventory = json.loads(INVENTORY.read_text())
    rows = inventory["tables"]
    assert len(rows) == 91
    assert len({row["table"] for row in rows}) == 91
    allowed = {
        "REQUIRED_NOW", "DERIVED_SAFELY", "REQUIRES_BACKFILL",
        "REQUIRES_DOMAIN_OWNER", "NOT_APPLICABLE",
    }
    for row in rows:
        assert row["authority"].endswith("OWNER")
        assert len(row["columns"]) == 9
        assert {item["classification"] for item in row["columns"]} <= allowed
        for item in row["columns"]:
            if item["classification"] == "DERIVED_SAFELY":
                assert "foreign" in item["reason"].lower()
    tenant = next(row for row in rows if row["table"] == "iam_tenant")
    classifications = {item["column"]: item["classification"] for item in tenant["columns"]}
    assert classifications["tenant_id"] == "NOT_APPLICABLE"
    assert classifications["workspace_id"] == "NOT_APPLICABLE"


def test_wave_manifest_reconciles_current_database_inventory():
    summary = json.loads(WAVES.read_text())
    assert summary["database_table_count_excluding_alembic"] == 91
    assert summary["fully_compliant"] == 11
    assert summary["root_scope_exceptions"] == 1
    assert summary["migration_candidates"] == 79
    tables = [table for wave in summary["waves"].values() for table in wave["tables"]]
    assert len(tables) == 91
    assert len(set(tables)) == 91
    assert "WAVE_5_AI_MEMORY_KNOWLEDGE_AND_TOOLS" not in summary["waves"]
    assert "WAVE_6_COMMERCIAL_USAGE_AND_BILLING" not in summary["waves"]


def test_restic_validator_fails_closed_before_network_access():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("runtime test image intentionally omits bash")
    result = subprocess.run(
        [bash, str(RESTIC)], text=True, capture_output=True, check=False,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )
    assert result.returncode == 2
    assert "BACKUP_REPOSITORY_FILE_MISSING" in result.stderr
    assert "password" not in result.stdout.lower()


def test_restic_validator_has_required_remote_proofs():
    text = RESTIC.read_text()
    for required in (
        "restic_cmd snapshots", "restic_cmd backup", "restic_cmd check",
        "restic_cmd restore", "sha256sum -c", "StrictHostKeyChecking=yes",
        "AWS_EC2_METADATA_DISABLED=true",
        "BACKUP_UPLOAD=PASS", "ISOLATED_RESTORE_FROM_OFFSITE=PASS",
    ):
        assert required in text

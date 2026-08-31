from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = (
    ROOT / "deploy" / "internal-n8n-private" / "compose.internal-n8n.yaml",
    ROOT / "deploy" / "internal-odoo" / "compose.internal-odoo.yaml",
)


def test_internal_proxies_reap_healthcheck_helpers_and_bound_pids() -> None:
    for compose_file in COMPOSE_FILES:
        compose = compose_file.read_text(encoding="utf-8")
        assert re.search(r"(?m)^    init: true$", compose), compose_file
        assert re.search(r"(?m)^    pids_limit: 256$", compose), compose_file
        assert re.search(r"(?m)^    read_only: true$", compose), compose_file
        assert "no-new-privileges:true" in compose
        assert re.search(r"(?ms)^    cap_drop:\s*(?:\[ALL\]|\n      - ALL)", compose)


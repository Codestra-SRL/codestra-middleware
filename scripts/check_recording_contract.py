#!/usr/bin/env python3
"""Fail CI when the recording contract drifts from the vendored PR A fixture."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "recording"
FIXTURE = SCHEMAS / "fixtures" / "pr-a-recording-contract-v1.json"


def main() -> int:
    contract = json.loads((SCHEMAS / "recording-contract-v1.json").read_text())
    fixture = json.loads(FIXTURE.read_text())
    if contract["contract_version"] != "1.0":
        raise SystemExit("recording contract version must remain 1.0")
    if contract["source_fixture"] != fixture["source_fixture"]:
        raise SystemExit("PR A fixture provenance drifted")
    reservation = json.loads((SCHEMAS / "recording-reservation-v1.json").read_text())
    exporter_fields = set(fixture["exporter_reservation_fields"])
    schema_fields = set(reservation["properties"])
    if not exporter_fields.issubset(schema_fields):
        raise SystemExit(
            f"PR A reservation shape drifted: missing {sorted(exporter_fields-schema_fields)}"
        )
    for name in contract["schemas"]:
        schema = json.loads((SCHEMAS / name).read_text())
        if schema["properties"]["contract_version"].get("const") != "1.0":
            raise SystemExit(f"{name}: contract version drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

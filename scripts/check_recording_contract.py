#!/usr/bin/env python3
"""Fail CI unless the five schemas match PR A exact head byte-for-byte."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "recording"
MANIFEST = SCHEMAS / "contract-manifest-v1.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    if manifest != {
        "contract_version": "1.0",
        "source_repository": "Codestra-SRL/telephony-event-gateway",
        "source_pull_request": 20,
        "source_head": "817299f2648be9b8c7c29ffd51645bf2e3a5a095",
        "schemas": manifest["schemas"],
    }:
        raise SystemExit("canonical recording provenance drifted")
    for name, expected in manifest["schemas"].items():
        actual = hashlib.sha256((SCHEMAS / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"{name}: PR A exact-head SHA-256 mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

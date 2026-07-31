#!/usr/bin/env python3
"""Discover official amd64 manifest digests and prepare review-only refreshes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".security" / "images.json"
REPORTS = ROOT / "reports" / "security"


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def main() -> None:
    document = json.loads(CONFIG.read_text())
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    changes: list[str] = []
    for image in document["images"]:
        if not image["official"]:
            raise SystemExit(f"{image['name']}: unofficial image rejected")
        tag = image["compatible_tag"]
        if tag.lower() in {"latest", "stable", "next", "nightly", "beta", "v3-nightly"}:
            raise SystemExit(f"{image['name']}: floating discovery channel rejected")
        manifest = json.loads(
            run(
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                f"{image['repository']}:{tag}",
                "--format",
                "{{json .Manifest}}",
            )
        )
        digest = manifest["digest"]
        reference = f"{image['repository']}@{digest}"
        rows.append(f"{image['name']}\t{reference}")
        if reference != image["reference"]:
            changes.append(f"{image['name']}: {image['reference']} -> {reference}")
            image["reference"] = reference
    CONFIG.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    (REPORTS / "images.tsv").write_text("\n".join(rows) + "\n")
    (REPORTS / "DIGEST-REPORT.md").write_text(
        "# Official Image Digest Report\n\n"
        + ("\n".join(f"- {line}" for line in changes) if changes else "- No digest changes.")
        + "\n"
    )


if __name__ == "__main__":
    main()

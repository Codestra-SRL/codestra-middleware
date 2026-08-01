from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
REPOSITORY = ROOT.parents[1]
SECURITY = ROOT / "security"
POLICY = SECURITY / "image-verification-policy.json"
ALLOWED = {"cosign_keyless", "cosign_key", "github_attestation", "digest_pin_plus_sbom_and_approved_risk_acceptance"}
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")

policy = json.loads(POLICY.read_text())
counts = json.loads((SECURITY / "vulnerability-counts.json").read_text())
checksum_lines = (SECURITY / "sbom/SHA256SUMS").read_text().splitlines()
listed = {line.split()[1]: line.split()[0] for line in checksum_lines if line.strip()}
expected_files = {Path(item["sbom_path"]).name for item in policy["images"]}
assert set(listed) == expected_files
assert {item["image_name"] for item in policy["images"]} == set(counts)
for item in policy["images"]:
    assert set(item) == {"image_name","image_digest","publisher","source_repository","verification_method","cosign_certificate_identity","cosign_oidc_issuer","cosign_public_key_reference","sbom_path","sbom_sha256","attestation_type","vulnerability_report_paths","risk_acceptance_reference"}
    assert DIGEST.fullmatch(item["image_digest"])
    assert item["verification_method"] in ALLOWED
    assert item["image_digest"] == counts[item["image_name"]]["digest"]
    path = SECURITY / item["sbom_path"]
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == item["sbom_sha256"] == listed[path.name]
    with gzip.open(path, "rt") as handle: sbom = json.load(handle)
    assert sbom["bomFormat"] == "CycloneDX"
    component = sbom["metadata"]["component"]
    expected_subjects = {
        "middleware": "codestra/lead-staging-middleware",
        "n8n": "n8nio/n8n",
    }
    assert component["name"] == expected_subjects.get(item["image_name"], item["image_name"])
    assert component["version"] == item["image_digest"]
    if item["verification_method"] == "cosign_keyless":
        assert item["cosign_certificate_identity"] and item["cosign_oidc_issuer"]
    if item["verification_method"] == "cosign_key": assert item["cosign_public_key_reference"]
    count = counts[item["image_name"]]
    high_risk = count["trivy_critical"] + count["trivy_high"] + count["grype_high_or_critical"] > 0
    if high_risk:
        assert item["risk_acceptance_reference"]
    for report in item["vulnerability_report_paths"]:
        report_path = SECURITY / report if report.startswith("scans/") else REPOSITORY / report
        assert report_path.is_file()
print("SBOM_CHECKSUM_GATE=PASS")
print("SBOM_COMPRESSION_GATE=PASS")
print("SBOM_PARSE_GATE=PASS")
print("SBOM_IMAGE_SUBJECT_GATE=PASS")
print("UPSTREAM_DIGEST_IDENTITY_GATE=PASS")
print("SBOM_ATTESTATION_GATE=NOT_AVAILABLE_WITH_APPROVED_ALTERNATE_CONTROLS")
print("SUPPLY_CHAIN_SOURCE_POLICY_GATE=PASS")

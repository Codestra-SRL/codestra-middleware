from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

UTC = dt.timezone(dt.timedelta())

ROOT = Path(__file__).parent
SECURITY = ROOT / "security"
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
SHA = re.compile(r"^[a-f0-9]{40}$")
STATUSES = {"security_owner_decision_required", "approved_for_staging"}
GATES = {
    "production_deployment_gate",
    "production_activation_gate",
    "server_b_access_gate",
    "customer_data_gate",
}
COMMON = {
    "schema_version",
    "status",
    "decision_subject",
    "middleware_source_sha",
    "odoo_source_sha",
    "image_manifest_sha256",
    *GATES,
    "created_at_utc",
    "updated_at_utc",
    "security_owner_acceptance_present",
    "approved_scope",
    "security_owner",
    "security_owner_authority_reference",
    "decision_timestamp_utc",
    "expiration_timestamp_utc",
    "approval_reference",
    "accepted_image_digests",
    "accepted_vulnerability_counts",
    "required_compensating_controls",
    "revocation_conditions",
    "external_human_approval_required",
    "document_is_not_external_approval",
}


def timestamp(value: str | None) -> dt.datetime | None:
    if value is None:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return dt.datetime.fromisoformat(normalized)


def validate_decision(
    document: dict[str, Any], now: dt.datetime, policy_sha: str, counts: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    unknown = set(document) - COMMON
    missing = COMMON - set(document)
    if unknown:
        errors.append("unknown properties: " + ", ".join(sorted(unknown)))
    if missing:
        errors.append("missing properties: " + ", ".join(sorted(missing)))
    if missing:
        return errors
    if document["schema_version"] != 1:
        errors.append("unsupported schema version")
    if document["status"] not in STATUSES:
        errors.append("unknown status")
    if not SHA.fullmatch(document["middleware_source_sha"]):
        errors.append("invalid middleware source SHA")
    if not SHA.fullmatch(document["odoo_source_sha"]):
        errors.append("invalid Odoo source SHA")
    if document["image_manifest_sha256"] != policy_sha:
        errors.append("image manifest digest mismatch")
    for gate in GATES:
        if document[gate] != "blocked":
            errors.append(f"{gate} must remain blocked")
    if (
        document["external_human_approval_required"] is not True
        or document["document_is_not_external_approval"] is not True
    ):
        errors.append("source document must disclaim external approval")
    try:
        created, updated = (
            timestamp(document["created_at_utc"]),
            timestamp(document["updated_at_utc"]),
        )
        if created is None or updated is None or updated < created:
            errors.append("invalid document timestamps")
    except (TypeError, ValueError):
        errors.append("invalid document timestamps")
    approval_fields = [
        "approved_scope",
        "security_owner",
        "security_owner_authority_reference",
        "decision_timestamp_utc",
        "expiration_timestamp_utc",
        "approval_reference",
        "accepted_image_digests",
        "accepted_vulnerability_counts",
        "required_compensating_controls",
        "revocation_conditions",
    ]
    if document["status"] == "security_owner_decision_required":
        if document["security_owner_acceptance_present"] is not False:
            errors.append("decision-required state cannot claim acceptance")
        if any(document[name] is not None for name in approval_fields):
            errors.append("decision-required approval fields must be null")
    elif document["status"] == "approved_for_staging":
        if document["security_owner_acceptance_present"] is not True:
            errors.append("approved state requires acceptance")
        if document["approved_scope"] != "server_a_isolated_staging":
            errors.append("approved scope mismatch")
        for name in approval_fields[1:6]:
            if not document[name]:
                errors.append(f"approved state requires {name}")
        digests = document["accepted_image_digests"] or {}
        expected_digests = {name: value["digest"] for name, value in counts.items()}
        if digests != expected_digests or any(
            not DIGEST.fullmatch(str(value)) for value in digests.values()
        ):
            errors.append("accepted image digest mismatch")
        if document["accepted_vulnerability_counts"] != counts:
            errors.append("accepted vulnerability count mismatch")
        if not document["required_compensating_controls"]:
            errors.append("compensating controls required")
        if not document["revocation_conditions"]:
            errors.append("revocation conditions required")
        try:
            decision_at, expires = (
                timestamp(document["decision_timestamp_utc"]),
                timestamp(document["expiration_timestamp_utc"]),
            )
            if decision_at is None or expires is None or expires <= decision_at:
                errors.append("expiration must follow decision")
            if expires is not None and expires <= now:
                errors.append("decision expired")
        except (TypeError, ValueError):
            errors.append("invalid approval timestamps")
    return errors


def validate_external(
    record: dict[str, Any],
    decision: dict[str, Any],
    expected_head: str,
    now: dt.datetime,
) -> list[str]:
    errors: list[str] = []
    required = {
        "record_type",
        "security_owner",
        "authority_reference",
        "pr_head",
        "image_digests",
        "vulnerability_counts",
        "scope",
        "decision",
        "decision_timestamp_utc",
        "expiration_timestamp_utc",
        "immutable_reference",
        "created_at_utc",
        "updated_at_utc",
        "signer_identity",
        "signer_oidc_issuer",
        "decision_signature_bundle",
    }
    if set(record) != required:
        errors.append("external record fields mismatch")
    if errors:
        return errors
    if record["record_type"] != "security_risk_acceptance":
        errors.append("ordinary code approval is not risk acceptance")
    if record["security_owner"] != decision["security_owner"]:
        errors.append("security owner mismatch")
    if record["authority_reference"] != decision["security_owner_authority_reference"]:
        errors.append("security owner authority mismatch")
    if record["decision"] != "accepted":
        errors.append("external risk decision is not accepted")
    if record["scope"] != "server_a_isolated_staging":
        errors.append("external scope mismatch")
    if record["pr_head"] != expected_head:
        errors.append("external approval is stale")
    if record["image_digests"] != decision["accepted_image_digests"]:
        errors.append("external digest binding mismatch")
    if record["vulnerability_counts"] != decision["accepted_vulnerability_counts"]:
        errors.append("external count binding mismatch")
    if record["created_at_utc"] != record["updated_at_utc"]:
        errors.append("edited external approval rejected")
    if not str(record["immutable_reference"]).startswith("github://"):
        errors.append("immutable audit reference required")
    if not str(record["signer_identity"]).startswith("https://github.com/Codestra-SRL/"):
        errors.append("invalid signer identity")
    if record["signer_oidc_issuer"] != "https://token.actions.githubusercontent.com":
        errors.append("invalid signer OIDC issuer")
    if not str(record["decision_signature_bundle"]).endswith(".bundle.json"):
        errors.append("Cosign decision signature bundle required")
    try:
        decided, expires = (
            timestamp(record["decision_timestamp_utc"]),
            timestamp(record["expiration_timestamp_utc"]),
        )
        if decided is None or expires is None or expires <= decided or expires <= now:
            errors.append("external approval expired or invalid")
        if record["decision_timestamp_utc"] != decision["decision_timestamp_utc"]:
            errors.append("external decision timestamp mismatch")
        if record["expiration_timestamp_utc"] != decision["expiration_timestamp_utc"]:
            errors.append("external expiration mismatch")
    except (TypeError, ValueError):
        errors.append("external timestamps invalid")
    return errors


def main() -> None:
    decision = json.loads((SECURITY / "image-security-decision.json").read_text())
    counts = json.loads((SECURITY / "vulnerability-counts.json").read_text())
    policy_sha = hashlib.sha256(
        (SECURITY / "image-verification-policy.json").read_bytes()
    ).hexdigest()
    errors = validate_decision(decision, dt.datetime.now(UTC), policy_sha, counts)
    if errors:
        raise SystemExit("\n".join(errors))
    print("SECURITY_DECISION_SCHEMA_GATE=PASS")
    print("SECURITY_DECISION_STATE_MACHINE_GATE=PASS")
    print(
        "SECURITY_OWNER_ACCEPTANCE_GATE="
        + (
            "SOURCE_APPROVED_EXTERNAL_GATE_REQUIRED"
            if decision["status"] == "approved_for_staging"
            else "PENDING"
        )
    )


if __name__ == "__main__":
    main()

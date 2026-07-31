"""Fail-closed recording retention decisions; execution is disabled by default."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os


POLICY_DAYS = {"synthetic_test": 7, "standard": 365, "high_compliance": 1825}
STATES = (
    "NOT_ELIGIBLE", "ELIGIBLE", "LEGAL_HOLD",
    "DELETION_AUTHORIZATION_PENDING", "DELETING", "DELETED",
    "FAILED", "QUARANTINED",
)


@dataclass(frozen=True)
class RetentionCandidate:
    recording_uid: str
    retention_class: str
    verified_at: datetime
    retention_expiration: datetime | None
    object_version: str
    checksum: str
    upload_verified: bool
    checksum_match: bool
    file_size_match: bool
    odoo_linked: bool
    quarantined: bool
    legal_hold: bool


def authorize_deletion(
    item: RetentionCandidate, *, now: datetime, local_copy: bool
) -> tuple[bool, str]:
    if item.retention_class not in {*POLICY_DAYS, "legal_hold"}:
        return False, "retention_policy_unresolved"
    if item.legal_hold or item.retention_class == "legal_hold":
        return False, "legal_hold"
    checks = (
        (item.upload_verified, "upload_not_verified"),
        (item.checksum_match, "checksum_mismatch"),
        (item.file_size_match, "file_size_mismatch"),
        (item.odoo_linked, "odoo_not_linked"),
        (not item.quarantined, "quarantined"),
    )
    for passed, reason in checks:
        if not passed:
            return False, reason
    eligible_at = (
        item.verified_at + timedelta(days=7)
        if local_copy else item.retention_expiration
    )
    if eligible_at is None:
        return False, "retention_expiration_missing"
    if now < eligible_at:
        return False, "not_expired"
    return True, "eligible"


def audit_record(item, *, authorized, reason, now, result):
    return {
        "recording_uid": item.recording_uid,
        "retention_class": item.retention_class,
        "retention_expiration": (
            item.retention_expiration.isoformat()
            if item.retention_expiration else None
        ),
        "checksum": item.checksum,
        "object_version": item.object_version,
        "authorization_decision": authorized,
        "authorization_reason": reason,
        "execution_time": now.isoformat(),
        "result": result,
        "audit_actor": "recording-retention-worker",
    }


def main() -> None:
    if os.getenv("RECORDING_RETENTION_EXECUTION_ENABLED", "false") != "false":
        raise SystemExit("deletion requires separate deployment authorization")
    print(json.dumps({"state": "NOT_ELIGIBLE", "at": datetime.now(UTC).isoformat()}))


if __name__ == "__main__":
    main()

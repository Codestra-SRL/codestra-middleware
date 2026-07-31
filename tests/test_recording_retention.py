from datetime import UTC, datetime, timedelta

from app.core.recording_retention import RetentionCandidate, authorize_deletion


NOW = datetime(2026, 7, 31, tzinfo=UTC)


def candidate(**changes):
    values = {
        "recording_uid": "rec_fixture",
        "retention_class": "standard",
        "verified_at": NOW - timedelta(days=8),
        "retention_expiration": NOW - timedelta(seconds=1),
        "object_version": "version_fixture",
        "checksum": "a" * 64,
        "upload_verified": True,
        "checksum_match": True,
        "file_size_match": True,
        "odoo_linked": True,
        "quarantined": False,
        "legal_hold": False,
    }
    values.update(changes)
    return RetentionCandidate(**values)


def test_not_before_local_grace_period():
    item = candidate(verified_at=NOW - timedelta(days=6))
    assert authorize_deletion(item, now=NOW, local_copy=True) == (
        False, "not_expired",
    )


def test_unverified_quarantine_and_legal_hold_fail_closed():
    assert not authorize_deletion(
        candidate(upload_verified=False), now=NOW, local_copy=True
    )[0]
    assert not authorize_deletion(
        candidate(quarantined=True), now=NOW, local_copy=True
    )[0]
    assert not authorize_deletion(
        candidate(legal_hold=True), now=NOW, local_copy=False
    )[0]


def test_expired_verified_object_is_eligible():
    assert authorize_deletion(candidate(), now=NOW, local_copy=False) == (
        True, "eligible",
    )

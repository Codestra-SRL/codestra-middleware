from pathlib import Path


WORKER = Path("app/workers/enterprise_events.py").read_text()
MIGRATION = Path("migrations/versions/0032_enterprise_core_completion.py").read_text()


def test_claim_is_atomic_and_multi_worker_safe():
    assert "FOR UPDATE SKIP LOCKED" in WORKER
    assert "status='LEASED'" in WORKER
    assert "lease_expires_at < now()" in WORKER


def test_delivery_is_exactly_once_per_subscription():
    assert "uq_event_delivery_once" in MIGRATION
    assert "ON CONFLICT (event_id, subscription_id) DO NOTHING" in WORKER


def test_retry_is_bounded_and_dead_letters():
    assert "attempts >= :max_attempts THEN 'DEAD_LETTER'" in WORKER
    assert "LEAST(300" in WORKER
    assert "min(max(max_attempts, 1), 10)" in WORKER


def test_worker_never_accepts_payload_or_endpoint_url():
    assert "payload" not in WORKER
    assert "httpx" not in WORKER
    assert "endpoint_key" not in WORKER


def test_governance_records_store_hashes_not_secrets():
    assert '"secret_hash"' in MIGRATION
    assert '"secret"' not in MIGRATION
    assert "iam_access_review" in MIGRATION

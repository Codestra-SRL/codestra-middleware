from uuid import uuid4
import pytest
from app.call_intelligence.domain import (
    CallJob,
    IdempotencyStore,
    InvalidTransition,
    JobStatus,
    redact_transcript,
)


def job():
    return CallJob(uuid4(), "171234.9", "call-1", "TEST_SYN", "agent1")


def test_events_are_idempotent():
    store = IdempotencyStore()
    original = job()
    first, created = store.create_job(original)
    duplicate, created_again = store.create_job(
        CallJob(
            original.tenant_id,
            original.vicidial_uniqueid,
            "other-event-id",
            "TEST_SYN",
            "agent1",
        )
    )
    assert created and not created_again and duplicate.id == first.id


def test_state_machine_and_audit():
    value = job()
    value.transition(JobStatus.RECORDING_PENDING, "test")
    value.transition(JobStatus.POLICY_BLOCKED, "policy")
    assert len(value.audit) == 2
    with pytest.raises(InvalidTransition):
        value.transition(JobStatus.ANALYZING, "test")


def test_redaction_is_complete_for_payment_and_secret_data():
    output, events = redact_transcript(
        "card 4111 1111 1111 1111 and CVV is 123 password is swordfish"
    )
    assert (
        "4111" not in output
        and "123" not in output
        and "swordfish" not in output
        and len(events) == 3
    )


def test_callback_replay_protection():
    store = IdempotencyStore()
    jid = uuid4()
    payload = b'{"result":"ok"}'
    assert store.accept_callback("analysis", jid, payload)
    assert not store.accept_callback("analysis", jid, payload)

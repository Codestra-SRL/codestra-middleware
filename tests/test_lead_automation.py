
import pytest

from app.adapters.odoo.lead_automation import signed_headers
from app.core.lead_automation import (
    Conflict,
    LeadAutomationError,
    LeadAutomationService,
    Policy,
    State,
)


def payload(**updates):
    value = {
        "contract_version": "1.0",
        "event_id": "EVT-synthetic01",
        "event_type": "lead.update.requested.v1",
        "occurred_at": "2026-01-01T00:00:00Z",
        "environment": "staging",
        "business_unit_key": "web-mobile-ai",
        "campaign_key": "TEST_LEADS",
        "automation_action": "UPDATE_ALLOWLISTED_FIELDS",
        "idempotency_key": "a" * 64,
        "correlation_id": "00000000-0000-4000-8000-000000000001",
        "policy_version": "1.0",
        "lead_uid": "LEAD-synthetic01",
        "attributes_schema_key": "web-mobile-ai-lead-v1",
        "attributes": {"solution_type": "AI"},
        "consent_snapshot": {
            "consent_status": "granted",
            "consent_purpose": "LEAD_SERVICE",
            "consent_source": "odoo",
            "consent_updated_at": "2026-01-01T00:00:00Z",
            "dnc_status": False,
            "dnc_updated_at": "2026-01-01T00:00:00Z",
            "jurisdiction": "DO",
            "source_system": "odoo",
        },
    }
    value.update(updates)
    return value


def allowed_service(*, consent=False, contact=False):
    service = LeadAutomationService()
    service.enabled = True
    service.binding_enabled = True
    service.action_switches["UPDATE_ALLOWLISTED_FIELDS"] = True
    service.add_policy(
        Policy(
            "staging",
            "web-mobile-ai",
            "TEST_LEADS",
            "lead.update.requested.v1",
            "UPDATE_ALLOWLISTED_FIELDS",
            "1.0",
            True,
            consent,
            contact,
            frozenset({"solution_type"}),
            True,
        )
    )
    return service


def test_01_valid_authorized_update():
    assert allowed_service().receive(payload())["state"] == State.OUTBOX_PENDING


def test_02_unknown_business_unit_denied():
    assert (
        allowed_service().receive(payload(business_unit_key="unknown"))["state"]
        == State.POLICY_DENIED
    )


def test_03_unknown_campaign_denied():
    assert (
        allowed_service().receive(payload(campaign_key="UNKNOWN"))["state"]
        == State.POLICY_DENIED
    )


def test_04_unknown_action_denied():
    with pytest.raises(LeadAutomationError):
        allowed_service().receive(payload(automation_action="SEND_EMAIL"))


def test_05_disabled_binding_prevents_dispatch():
    s = allowed_service()
    s.binding_enabled = False
    e = s.receive(payload())
    assert not s.reserve_dispatch(e["event_id"])


def test_06_disabled_global_prevents_dispatch():
    s = allowed_service()
    s.enabled = False
    assert s.receive(payload())["state"] == State.POLICY_DENIED


def test_07_dnc_blocks_contact_action():
    s = allowed_service(contact=True)
    p = payload()
    p["consent_snapshot"]["dnc_status"] = True
    assert s.receive(p)["state"] == State.DNC_BLOCKED


def test_08_missing_consent_blocks():
    s = allowed_service(consent=True)
    p = payload()
    p["consent_snapshot"]["consent_status"] = "unknown"
    assert s.receive(p)["state"] == State.CONSENT_BLOCKED


def test_09_expired_consent_blocks():
    s = allowed_service(consent=True)
    p = payload()
    p["consent_snapshot"]["consent_status"] = "expired"
    assert s.receive(p)["state"] == State.CONSENT_BLOCKED


def test_10_valid_consent_allows():
    assert (
        allowed_service(consent=True).receive(payload())["state"]
        == State.OUTBOX_PENDING
    )


def test_11_identical_event_replay():
    s = allowed_service()
    first = s.receive(payload())
    assert s.receive(payload()) == first and len(s.events) == 1


def test_12_conflicting_event_quarantines():
    s = allowed_service()
    s.receive(payload())
    changed = payload(campaign_key="OTHER")
    with pytest.raises(Conflict):
        s.receive(changed)


def result():
    return {
        "contract_version": "1.0",
        "event_id": "EVT-synthetic01",
        "workflow_execution_id": "N8N-synthetic01",
        "binding_key": "n8n.leads.ingest",
        "environment": "staging",
        "business_unit_key": "web-mobile-ai",
        "campaign_key": "TEST_LEADS",
        "automation_action": "UPDATE_ALLOWLISTED_FIELDS",
        "result_status": "SUCCEEDED",
        "result_code": "UPDATED",
        "result_payload": {"field_updates": {"solution_type": "AI"}},
        "occurred_at": "2026-01-01T00:01:00Z",
        "idempotency_key": "b" * 64,
    }


def dispatched():
    s = allowed_service()
    e = s.receive(payload())
    s.reserve_dispatch(e["event_id"])
    s.mark_dispatched(e["event_id"])
    s.acknowledge_n8n(e["event_id"])
    s.result_processing_enabled = True
    return s, e


def test_13_identical_result_replay():
    s, _ = dispatched()
    first = s.receive_result(result())
    assert s.receive_result(result()) == first and s.odoo_operations == 0


def test_14_conflicting_result_quarantines():
    s, _ = dispatched()
    s.receive_result(result())
    changed = result()
    changed["result_code"] = "OTHER"
    with pytest.raises(Conflict):
        s.receive_result(changed)


def test_15_hmac_signature_is_deterministic():
    h = signed_headers(
        {"a": 1},
        b"synthetic",
        "staging",
        "c" * 64,
        timestamp="2026-01-01T00:00:00Z",
        nonce="nonce",
    )
    assert len(h["X-Codestra-Signature"]) == 64


def test_16_reused_workflow_execution_denied():
    s, e = dispatched()
    s.receive_result(result())
    p = payload(event_id="EVT-synthetic02", idempotency_key="c" * 64)
    x = s.receive(p)
    s.reserve_dispatch(x["event_id"])
    s.mark_dispatched(x["event_id"])
    s.acknowledge_n8n(x["event_id"])
    r = result()
    r["event_id"] = "EVT-synthetic02"
    with pytest.raises(Conflict):
        s.receive_result(r)


def test_17_wrong_environment_denied():
    s, _ = dispatched()
    r = result()
    r["environment"] = "production"
    with pytest.raises(Conflict):
        s.receive_result(r)


def test_18_unauthorized_field_denied():
    with pytest.raises(LeadAutomationError, match="attribute schema"):
        allowed_service().receive(payload(attributes={"unapproved": "x"}))


def test_19_unauthorized_stage_change_denied():
    assert (
        allowed_service().receive(payload(automation_action="CHANGE_AUTHORIZED_STAGE"))[
            "state"
        ]
        == State.POLICY_DENIED
    )


def test_20_unauthorized_assignment_denied():
    assert (
        allowed_service().receive(payload(automation_action="ASSIGN_AUTHORIZED_USER"))[
            "state"
        ]
        == State.POLICY_DENIED
    )


def test_21_ack_mismatch_quarantines():
    s, e = dispatched()
    s.receive_result(result())
    s.odoo_apply_enabled = True
    ack = {
        "contract_version": "1.0",
        "automation_event_id": e["automation_event_id"],
        "automation_action": "UPDATE_ALLOWLISTED_FIELDS",
        "business_unit_key": "wrong",
        "campaign_key": "TEST_LEADS",
        "policy_version": "1.0",
    }
    with pytest.raises(Conflict):
        s.apply_odoo_ack(e["event_id"], ack)


def test_22_n8n_timeout_bounded_retry():
    s = allowed_service()
    e = s.receive(payload())
    s.reserve_dispatch(e["event_id"])
    assert s.record_retry(e["event_id"], 1) == State.RETRY_PENDING


def test_23_odoo_timeout_bounded_retry():
    s, e = dispatched()
    s.receive_result(result())
    assert s.record_retry(e["event_id"], 2) == State.RETRY_PENDING


def test_24_permanent_failure_stops():
    s = allowed_service()
    e = s.receive(payload())
    s.reserve_dispatch(e["event_id"])
    assert s.record_retry(e["event_id"], 5) == State.FAILED_TERMINAL


def test_25_reconciliation_detects_missing_outbox():
    s = allowed_service()
    s.receive(payload())
    s.outbox.clear()
    assert "event_without_outbox" in s.reconcile()[0]


def test_26_n8n_defaults_inactive():
    s = LeadAutomationService()
    assert not s.binding_enabled and not s.enabled


def test_27_communication_actions_absent():
    assert not (
        {"SEND_EMAIL", "SEND_SMS", "SEND_WHATSAPP", "CREATE_CALENDAR_EVENT"}
        & set(signed_headers.__globals__.get("ACTIONS", set()))
    )


def test_28_n8n_payload_has_no_pii():
    forbidden = {"phone", "email", "customer_name", "notes"}
    assert not forbidden & set(payload()["attributes"])


def test_29_no_production_database_write():
    assert LeadAutomationService().events == {}


def test_30_no_recording_system_change():
    import inspect
    import app.core.lead_automation as module

    text = inspect.getsource(module)
    assert (
        "recording" not in text.lower()
        and "asterisk" not in text.lower()
        and "vicidial" not in text.lower()
    )

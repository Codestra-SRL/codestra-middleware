from app.api.v1.events import VicidialEvent


def test_canonical_synthetic_envelope_maps_to_test_campaign():
    event = {
        "schema_version": "1.0",
        "event_id": "39df611e-528a-4dc2-9795-1573fd963477",
        "event_type": "vicidial.test.synthetic",
        "occurred_at": "2026-07-24T00:00:00Z",
        "correlation_id": "phase2-regression",
        "test_syn": True,
        "payload": {
            "probe_id": "phase2-regression",
            "marker": "TEST_SYN",
            "generated_at": "2026-07-24T00:00:00Z",
        },
    }

    parsed = VicidialEvent.model_validate(event)

    assert parsed.uniqueid == event["event_id"]
    assert parsed.lead_id == 0
    assert parsed.campaign_id == "TEST_SYN"
    assert parsed.model_dump()["payload"] == event["payload"]


def test_noncanonical_synthetic_envelope_remains_rejected():
    event = {
        "schema_version": "1.0",
        "event_id": "39df611e-528a-4dc2-9795-1573fd963477",
        "event_type": "vicidial.test.synthetic",
        "test_syn": True,
        "payload": {"marker": "NOT_APPROVED"},
    }

    try:
        VicidialEvent.model_validate(event)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid synthetic envelope was accepted")

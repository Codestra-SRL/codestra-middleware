import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).with_name("replay_v3.py")
SPEC = importlib.util.spec_from_file_location("replay_v3", MODULE_PATH)
replay = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(replay)


def rows():
    result = []
    for event_type, status in zip(replay.EVENT_ORDER, ("STARTED", "CONNECTED", "ENDED")):
        payload = {"lifecycle_status": status, "disposition": None, "hangup_cause": None}
        event = {
            "schema_version": "1.0",
            "event_id": hashlib.md5(event_type.encode()).hexdigest(),
            "event_type": event_type,
            "occurred_at": "2026-07-28T01:06:49Z",
            "correlation_id": "1785200809.1",
            "client_instance": replay.CLIENT,
            "source_system": "asterisk-ami",
            "producer_instance_id": "server-b",
            "producer_boot_id": "boot",
            "payload_sha256": hashlib.sha256(replay.canonical(payload)).hexdigest(),
            "asterisk_unique_id": "1785200809.1",
            "asterisk_linked_id": "1785200809.1",
            "channel": "PJSIP/endpoint-6198-test",
            "source_extension": "6198",
            "destination": "*43",
            "dialplan_context": "cs-synth-6198",
            "payload": payload,
        }
        result.append({"payload": event})
    return result


def write(tmp_path, value):
    path = tmp_path / "events.json"
    path.write_text(json.dumps(value))
    return path


def test_exact_three_events_and_byte_identical_terminal_replay(tmp_path):
    events = replay.load_events(write(tmp_path, rows()), "1785200809.1")
    plan = (*events, events[-1])
    assert len(plan) == 4
    assert plan[2][1] == plan[3][1]
    assert [item[0]["event_type"] for item in events] == list(replay.EVENT_ORDER)


@pytest.mark.parametrize("mutation", ["extra", "order", "linked", "hash", "marker"])
def test_selection_fails_closed(tmp_path, mutation):
    value = rows()
    if mutation == "extra":
        value.append(value[-1])
    elif mutation == "order":
        value[0], value[1] = value[1], value[0]
    elif mutation == "linked":
        value[0]["payload"]["asterisk_linked_id"] = "other"
    elif mutation == "hash":
        value[0]["payload"]["payload_sha256"] = "0" * 64
    else:
        value[0]["payload"]["TEST_EVIDENCE_ID"] = "forbidden"
    with pytest.raises(SystemExit):
        replay.load_events(write(tmp_path, value), "1785200809.1")


def test_url_restrictions():
    assert replay.validate_url("http://127.0.0.1/api/v1/events/vicidial")
    with pytest.raises(SystemExit):
        replay.validate_url("http://10.40.0.1/api/v1/events/vicidial")
    with pytest.raises(SystemExit):
        replay.validate_url("https://example.test/wrong")


def test_target_identity_is_event_gateway(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self, _limit):
            return json.dumps({"service": replay.EXPECTED_SERVICE}).encode()

    monkeypatch.setattr(replay.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    replay.verify_target("http://127.0.0.1:8095/api/v1/events/vicidial")


def test_target_identity_rejects_integration_api(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self, _limit):
            return b'{"service":"middleware-integration-api"}'

    monkeypatch.setattr(replay.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(SystemExit):
        replay.verify_target("http://127.0.0.1:8095/api/v1/events/vicidial")

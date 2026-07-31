import json

import httpx

from app.adapters.recording_odoo import OdooRecordingWriter


def test_odoo_writer_is_signed_and_idempotency_bound():
    def handler(request):
        assert request.headers["x-codestra-signature"]
        assert request.headers["x-codestra-event-id"] == "REC-fixture"
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "recording_uid": body["recording_uid"],
                "state": "ODOO_LINKED",
            },
        )

    writer = OdooRecordingWriter(
        "https://odoo.internal/codestra/api/v1/recordings",
        b"x" * 32,
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert writer.upsert({"recording_uid": "REC-fixture"}) == "REC-fixture"

import hashlib
import hmac
import http.client
import json
import os
import ssl
import time
import uuid

secret = open(os.environ.get("CALLBACK_SECRET", "/run/secrets/callback_hmac"), "rb").read().strip()
context = ssl._create_unverified_context()


def call(event_id: str, nonce: str, *, signature=True, scope="callbacks:write"):
    body = json.dumps({"event_id": event_id, "workflow_code": "CDA-TEST-00", "status": "SUCCEEDED"}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    material = timestamp.encode() + b"." + nonce.encode() + b".codestra-n8n-staging." + scope.encode() + b"." + body
    sig = hmac.new(secret, material, hashlib.sha256).hexdigest() if signature else "00" * 32
    client = http.client.HTTPSConnection("127.0.0.1", 8443, context=context, timeout=3)
    started = time.perf_counter_ns()
    client.request("POST", "/callbacks/staging/result", body=body, headers={"Content-Type": "application/json", "Content-Length": str(len(body)), "X-Codestra-Identity": "codestra-n8n-staging", "X-Codestra-Scope": scope, "X-Codestra-Nonce": nonce, "X-Codestra-Timestamp": timestamp, "X-Codestra-Signature": sig})
    response = client.getresponse()
    response.read()
    client.close()
    return response.status, (time.perf_counter_ns() - started) / 1e6


replay_event = "section6-replay-" + uuid.uuid4().hex
replay_nonce = "nonce-" + uuid.uuid4().hex
valid, valid_ms = call("section6-valid-" + uuid.uuid4().hex, "nonce-" + uuid.uuid4().hex)
replay_first, _ = call(replay_event, replay_nonce)
replay_second, replay_ms = call(replay_event, replay_nonce)
invalid, _ = call("section6-invalid-" + uuid.uuid4().hex, "nonce-" + uuid.uuid4().hex, signature=False)
wrong_scope, _ = call("section6-scope-" + uuid.uuid4().hex, "nonce-" + uuid.uuid4().hex, scope="wrong:scope")
print(f"VALID_STATUS={valid}")
print(f"REPLAY_FIRST_STATUS={replay_first}")
print(f"REPLAY_SECOND_STATUS={replay_second}")
print(f"INVALID_SIGNATURE_STATUS={invalid}")
print(f"WRONG_SCOPE_STATUS={wrong_scope}")
print(f"CALLBACK_VALID_LATENCY_MS={valid_ms:.3f}")
print(f"CALLBACK_REPLAY_LATENCY_MS={replay_ms:.3f}")

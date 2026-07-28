#!/usr/bin/env python3
"""Fail-closed four-submission lifecycle replay tool."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

EVENT_ORDER = (
    "vicidial.call.started",
    "vicidial.call.connected",
    "vicidial.call.ended",
)
INGRESS_PATH = "/api/v1/events/vicidial"
CLIENT = "vicidial-server-b"
EXPECTED_SERVICE = "middleware-event-gateway"


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_events(path: Path, linked_id: str) -> list[tuple[dict[str, Any], bytes]]:
    if path.is_symlink() or not path.is_file():
        fail("events input must be a regular non-symlink file")
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or len(rows) != 3:
        fail("exactly three outbox rows are required")
    result = []
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
            fail("each outbox row must contain one envelope in payload")
        event = row["payload"]
        if event.get("event_type") != EVENT_ORDER[index]:
            fail("events are not in started, connected, ended order")
        if event.get("asterisk_linked_id") != linked_id:
            fail("event LinkedID does not match the authorized tuple")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or event_id in seen:
            fail("event IDs must be non-empty and unique")
        seen.add(event_id)
        payload = event.get("payload")
        expected_hash = event.get("payload_sha256")
        if not isinstance(payload, dict) or hashlib.sha256(canonical(payload)).hexdigest() != expected_hash:
            fail("payload integrity hash mismatch")
        if any("test_evidence_id" in str(key).lower() for key in event):
            fail("test evidence markers are forbidden in envelopes")
        result.append((event, canonical(event)))
    return result


def protected_secret(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        fail("secret must be a regular non-symlink file")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        fail("secret file permissions are too broad")
    value = path.read_text().strip()
    if not value or any(ord(char) < 32 for char in value):
        fail("secret is empty or contains control characters")
    return value


def validate_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.path != INGRESS_PATH or parsed.query or parsed.fragment:
        fail("target must be the exact VICIdial ingress path")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        fail("non-loopback execution requires HTTPS")
    if parsed.scheme not in {"http", "https"}:
        fail("unsupported target scheme")
    return value


def verify_target(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    version_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/version", "", "")
    )
    try:
        with urllib.request.urlopen(version_url, timeout=5) as response:
            value = json.loads(response.read(16384))
    except Exception as exc:
        fail(f"target identity check failed: {type(exc).__name__}")
    if value.get("service") != EXPECTED_SERVICE:
        fail("target is not the RC4 middleware event gateway")


def request(url: str, body: bytes, secret: str, event_id: str, response_log: Path) -> int:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(24)
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": event_id,
            "X-Signature": f"sha256={signature}",
            "X-Timestamp": timestamp,
            "X-Client-Instance-ID": CLIENT,
            "X-Nonce": nonce,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.status
            response_body = response.read(16384)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        response_body = exc.read(16384)
    record = {
        "attempt": sum(1 for _ in response_log.open()) + 1,
        "event_id": event_id,
        "request_body_sha256": hashlib.sha256(body).hexdigest(),
        "status": status_code,
        "response_sha256": hashlib.sha256(response_body).hexdigest(),
    }
    with response_log.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return status_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--expected-linked-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--secret-file", type=Path)
    parser.add_argument("--response-log", type=Path)
    parser.add_argument("--maximum-submissions", type=int, default=4)
    args = parser.parse_args()
    if args.maximum_submissions != 4:
        fail("maximum submissions must equal four")
    events = load_events(args.events, args.expected_linked_id)
    plan = [
        {"event_type": event["event_type"], "event_id": event["event_id"],
         "body_sha256": hashlib.sha256(body).hexdigest()}
        for event, body in (*events, events[-1])
    ]
    if not args.execute:
        print(json.dumps({"mode": "dry-run", "submission_count": 4, "plan": plan}, sort_keys=True))
        return 0
    if not args.url or not args.secret_file or not args.response_log:
        fail("execute requires url, secret-file, and response-log")
    url = validate_url(args.url)
    verify_target(url)
    if args.response_log.exists():
        fail("response log must not already exist")
    args.response_log.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.response_log.touch(mode=0o600, exist_ok=False)
    secret = protected_secret(args.secret_file)
    attempts = 0
    for event, body in (*events, events[-1]):
        attempts += 1
        status_code = request(url, body, secret, event["event_id"], args.response_log)
        if status_code not in {200, 201, 202}:
            fail(f"submission {attempts} failed; automatic retry is disabled")
    if attempts != 4:
        fail("submission count invariant failed")
    print("HTTP_SUBMISSION_COUNT=4")
    return 0


if __name__ == "__main__":
    sys.exit(main())

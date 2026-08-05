"""Call Intelligence state, schemas, redaction and safe identity helpers."""
from __future__ import annotations

import re
from typing import Any

CALL_STATES = frozenset({
    "CALL_COMPLETED", "RECORDING_PENDING", "RECORDING_AVAILABLE", "TRANSCRIPTION_QUEUED",
    "TRANSCRIBING", "TRANSCRIBED", "ANALYSIS_QUEUED", "ANALYZING", "ANALYZED",
    "QA_REVIEW_REQUIRED", "QA_REVIEWED", "ODOO_UPDATE_QUEUED", "ODOO_UPDATING",
    "COMPLETED", "RETRY_SCHEDULED", "FAILED", "UNKNOWN", "CANCELLED", "POLICY_BLOCKED",
})
TRANSITIONS: dict[str, frozenset[str]] = {
    "CALL_COMPLETED": frozenset({"RECORDING_PENDING", "POLICY_BLOCKED"}),
    "RECORDING_PENDING": frozenset({"RECORDING_AVAILABLE", "RETRY_SCHEDULED", "POLICY_BLOCKED"}),
    "RECORDING_AVAILABLE": frozenset({"TRANSCRIPTION_QUEUED"}),
    "TRANSCRIPTION_QUEUED": frozenset({"TRANSCRIBING", "CANCELLED"}),
    "TRANSCRIBING": frozenset({"TRANSCRIBED", "RETRY_SCHEDULED", "FAILED", "UNKNOWN"}),
    "TRANSCRIBED": frozenset({"ANALYSIS_QUEUED"}),
    "ANALYSIS_QUEUED": frozenset({"ANALYZING", "CANCELLED"}),
    "ANALYZING": frozenset({"ANALYZED", "RETRY_SCHEDULED", "FAILED"}),
    "ANALYZED": frozenset({"QA_REVIEW_REQUIRED", "ODOO_UPDATE_QUEUED"}),
    "QA_REVIEW_REQUIRED": frozenset({"QA_REVIEWED", "CANCELLED"}),
    "QA_REVIEWED": frozenset({"ODOO_UPDATE_QUEUED"}),
    "ODOO_UPDATE_QUEUED": frozenset({"ODOO_UPDATING", "CANCELLED"}),
    "ODOO_UPDATING": frozenset({"COMPLETED", "RETRY_SCHEDULED", "FAILED", "UNKNOWN"}),
    "RETRY_SCHEDULED": frozenset({"RECORDING_PENDING", "TRANSCRIPTION_QUEUED", "ANALYSIS_QUEUED", "ODOO_UPDATE_QUEUED", "CANCELLED"}),
    "UNKNOWN": frozenset({"COMPLETED", "FAILED", "RETRY_SCHEDULED"}),
}


class CallIntelligenceError(ValueError):
    pass


def transition(current: str, target: str) -> str:
    if current not in CALL_STATES or target not in CALL_STATES or target not in TRANSITIONS.get(current, frozenset()):
        raise CallIntelligenceError(f"invalid call intelligence transition: {current} -> {target}")
    return target


def canonical_key(tenant_id: str, uniqueid: str) -> str:
    if not tenant_id or not uniqueid or len(uniqueid) > 128:
        raise CallIntelligenceError("tenant and VICIdial uniqueid are required")
    return f"codestra:{tenant_id}:call:{uniqueid}"


def redact_text(text: str) -> tuple[str, list[str]]:
    redactions: list[str] = []
    patterns = [
        (r"\b(?:\d[ -]*?){13,19}\b", "PAYMENT_CARD"),
        (r"\b\d{9,17}\b", "SENSITIVE_NUMBER"),
        (r"(?i)\b(?:password|passcode|security\s+code)\s*[:=]\s*\S+", "AUTH_SECRET"),
    ]
    output = text or ""
    for pattern, label in patterns:
        output, count = re.subn(pattern, f"[{label}_REDACTED]", output)
        if count:
            redactions.extend([label] * count)
    return output, redactions


def validate_transcript(payload: dict[str, Any]) -> None:
    required = {"job_id", "language", "language_confidence", "segments", "model_code", "model_version"}
    if not required.issubset(payload):
        raise CallIntelligenceError("transcript schema is missing required fields")
    if not 0 <= float(payload["language_confidence"]) <= 1:
        raise CallIntelligenceError("language confidence must be between 0 and 1")
    if not isinstance(payload["segments"], list) or len(payload["segments"]) > 10000:
        raise CallIntelligenceError("transcript segments are invalid")
    for segment in payload["segments"]:
        if segment.get("speaker") not in {"AGENT", "CUSTOMER", "UNKNOWN", "SPEAKER_1", "SPEAKER_2"}:
            raise CallIntelligenceError("unsupported transcript speaker")
        if not isinstance(segment.get("text"), str) or len(segment["text"]) > 10000:
            raise CallIntelligenceError("transcript segment text is invalid")


def validate_analysis(payload: dict[str, Any]) -> None:
    required = {"summary", "customer_sentiment", "agent_sentiment", "callback", "confidence"}
    if not required.issubset(payload):
        raise CallIntelligenceError("analysis schema is missing required fields")
    sentiments = {"POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED", "UNKNOWN"}
    if payload["customer_sentiment"] not in sentiments or payload["agent_sentiment"] not in sentiments:
        raise CallIntelligenceError("invalid sentiment")
    if not 0 <= float(payload["confidence"]) <= 1:
        raise CallIntelligenceError("analysis confidence must be between 0 and 1")
    if not isinstance(payload["callback"], dict) or not isinstance(payload["callback"].get("recommended"), bool):
        raise CallIntelligenceError("callback recommendation is invalid")

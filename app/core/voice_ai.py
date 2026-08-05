"""Fail-closed Voice AI policy and authorization contracts."""
from dataclasses import dataclass

VOICE_STATES = frozenset({"REQUESTED", "POLICY_CHECKING", "AUTHORIZED", "QUEUED", "DIALING", "RINGING", "CONNECTED", "DISCLOSURE_PENDING", "DISCLOSURE_COMPLETE", "LISTENING", "PROCESSING", "SPEAKING", "TRANSFER_REQUESTED", "TRANSFERRING", "TRANSFERRED", "CALLBACK_REQUESTED", "ENDING", "COMPLETED", "NO_ANSWER", "BUSY", "REJECTED", "FAILED", "UNKNOWN", "CANCELLED", "POLICY_BLOCKED"})
ALLOWED_DISPOSITIONS = frozenset({"AI_COMPLETED", "AI_TRANSFERRED", "CALLBACK_SCHEDULED", "NO_ANSWER", "BUSY", "VOICEMAIL", "CUSTOMER_DECLINED", "WRONG_NUMBER", "DO_NOT_CALL", "UNQUALIFIED", "QUALIFIED", "APPOINTMENT_REQUESTED", "FAILED_TECHNICAL"})


class VoicePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class CallAuthorization:
    tenant_id: str
    campaign_code: str
    phone: str
    approved_number: bool
    suppressed: bool
    do_not_call: bool
    within_calling_window: bool
    attempts: int
    maximum_attempts: int
    outbound_enabled: bool
    emergency_stop: bool


def authorize_outbound(request: CallAuthorization) -> bool:
    if not request.tenant_id or not request.campaign_code or not request.phone:
        raise VoicePolicyError("identity and phone required")
    if any((not request.approved_number, request.suppressed, request.do_not_call, not request.within_calling_window, request.attempts >= request.maximum_attempts, not request.outbound_enabled, request.emergency_stop)):
        return False
    return True


def validate_disposition(disposition: str) -> str:
    if disposition not in ALLOWED_DISPOSITIONS:
        raise VoicePolicyError("disposition not allowed by policy")
    return disposition

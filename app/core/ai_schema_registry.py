"""Fail-closed registry for the control-plane result contracts."""

from typing import Any

REGISTERED_OUTPUT_SCHEMAS = frozenset(
    {
        "lead_discovery_v1",
        "lead_normalization_v1",
        "lead_verification_v1",
        "lead_score_v1",
        "odoo_import_result_v1",
        "ai_error_result_v1",
    }
)


def validate_result_schema(schema_code: str | None, payload: dict[str, Any] | None) -> None:
    """Validate the registry identity and common bounded fields.

    Detailed schemas are persisted in ``ai_output_schema``; this guard prevents
    unregistered result types from entering the inbox before a schema lookup.
    """
    if schema_code is None:
        return
    if schema_code not in REGISTERED_OUTPUT_SCHEMAS:
        raise ValueError("unknown AI output schema")
    if payload is None:
        raise ValueError("schema payload is required")
    confidence = payload.get("confidence")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    score = payload.get("lead_score")
    if score is not None and not 0 <= score <= 100:
        raise ValueError("lead_score must be between 0 and 100")

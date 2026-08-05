"""Allowlisted CRM lead mapping for controlled staging imports."""

from __future__ import annotations

from typing import Any

ALLOWED_MODEL = "crm.lead"
ALLOWED_FIELDS = frozenset(
    {
        "name", "partner_name", "phone", "mobile", "email_from", "website", "street",
        "city", "zip", "country_id", "description", "team_id", "user_id", "type",
        "x_codestra_external_key", "x_codestra_lead_record_id", "x_codestra_import_batch_id",
        "x_codestra_source", "x_codestra_source_urls", "x_codestra_source_evidence",
        "x_codestra_lead_score", "x_codestra_contact_confidence", "x_codestra_email_verification",
        "x_codestra_phone_verification", "x_codestra_duplicate_status", "x_codestra_ownership_status",
        "x_codestra_ai_summary", "x_codestra_reviewed_by", "x_codestra_reviewed_at", "x_codestra_imported_at",
    }
)


def map_lead_to_odoo(lead: dict[str, Any], *, external_key: str, batch_id: str, reviewer: str) -> dict[str, Any]:
    """Map only explicitly allowlisted CRM fields; never pass arbitrary keys."""
    company = lead.get("normalized_company_name") or lead.get("company_name")
    if not company:
        raise ValueError("company name is required")
    phones = lead.get("phones") or []
    address = lead.get("address_payload") or {}
    mapped = {
        "name": company,
        "partner_name": company,
        "phone": lead.get("normalized_phone") or lead.get("phone") or (phones[0] if phones else False),
        "email_from": lead.get("normalized_email") or lead.get("email") or False,
        "website": lead.get("website") or False,
        "street": address.get("street") or False,
        "city": address.get("city") or False,
        "zip": address.get("postal_code") or False,
        "description": lead.get("summary") or "Imported from approved Codestra Lead Intelligence review.",
        "type": "lead",
        "x_codestra_external_key": external_key,
        "x_codestra_lead_record_id": str(lead.get("id", "")),
        "x_codestra_import_batch_id": batch_id,
        "x_codestra_source": "codestra_lead_intelligence",
        "x_codestra_source_urls": lead.get("source_urls") or [],
        "x_codestra_source_evidence": lead.get("source_history") or [],
        "x_codestra_lead_score": lead.get("lead_score") or 0,
        "x_codestra_contact_confidence": lead.get("ownership_confidence") or 0,
        "x_codestra_duplicate_status": lead.get("duplicate_status") or "UNREVIEWED",
        "x_codestra_ownership_status": lead.get("ownership_status") or "UNKNOWN",
        "x_codestra_ai_summary": lead.get("summary") or False,
        "x_codestra_reviewed_by": reviewer,
    }
    return {key: value for key, value in mapped.items() if key in ALLOWED_FIELDS}


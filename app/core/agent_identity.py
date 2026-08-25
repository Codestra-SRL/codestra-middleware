"""Shared authenticated-agent identity resolution for browser-facing APIs.

The validation logic (Keycloak token → active-employee attribute lookup) was
originally embedded inline in the webphone provisioning gate. It is factored
out here so new agent-facing endpoints (interaction result persistence,
click-to-call) authenticate identically without duplicating security-relevant
logic. The webphone module keeps its own inline copy for now to avoid
regressing the existing staging gate in the same change that introduces this
helper; a follow-up should have it call into this module instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.api.v1.webphone import _attribute, _keycloak_user
from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator

AGENT_ROLES = frozenset({"codestra_agent", "codestra_closer", "codestra_supervisor"})


@dataclass(frozen=True)
class AgentIdentity:
    subject: str
    employee_id: str
    odoo_employee_id: str
    vicidial_username: str
    role: str
    business_unit_id: str
    tenant_id: str


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    forwarded_id_token = request.headers.get("x-forwarded-id-token", "")
    forwarded_access_token = request.headers.get(
        "x-forwarded-access-token", ""
    ) or request.headers.get("x-auth-request-access-token", "")
    if forwarded_id_token.strip():
        token = forwarded_id_token
    elif forwarded_access_token.strip():
        token = forwarded_access_token
    else:
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator:
            token = ""
    if not token.strip():
        raise HTTPException(401, "bearer authorization required")
    return token.strip()


async def authenticate_agent(request: Request) -> AgentIdentity:
    """Resolve and validate the authenticated agent making this request.

    Raises HTTPException(401/403/503) on any failure. Never returns a
    partial or unverified identity.
    """
    token = _bearer_token(request)
    try:
        validator = KeycloakValidator(
            issuer=settings.keycloak_issuer,
            audience=settings.keycloak_audience,
            jwks_url=settings.keycloak_jwks_url,
            authorized_parties=frozenset(
                value.strip()
                for value in settings.keycloak_authorized_parties.split(",")
                if value.strip()
            ),
            required_roles=frozenset(),
        )
        claims = validator.validate(token)
    except JWTAuthError as exc:
        raise HTTPException(401, "identity token rejected") from exc
    if claims.get("typ") not in {"ID", "Bearer"}:
        raise HTTPException(401, "agent identity token required")
    roles = set(claims.get("realm_access", {}).get("roles", []))
    roles.update(claims.get("roles", []))
    if not roles.intersection(AGENT_ROLES):
        raise HTTPException(403, "agent role required")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        proxy_subject = (
            request.headers.get("x-forwarded-user", "")
            or request.headers.get("x-auth-request-user", "")
        ).strip()
        subject = proxy_subject or None
    if not subject:
        raise HTTPException(401, "identity subject missing")
    user = await _keycloak_user(subject)
    attributes = user.get("attributes")
    if not isinstance(attributes, dict) or user.get("enabled") is not True:
        raise HTTPException(403, "active employee identity required")
    if _attribute(attributes, "lifecycle_state") != "active":
        raise HTTPException(403, "active employment required")
    employee_id = _attribute(attributes, "employee_id")
    vicidial_username = _attribute(attributes, "vicidial_username") or user.get(
        "username"
    )
    if not employee_id or not isinstance(vicidial_username, str) or not vicidial_username:
        raise HTTPException(403, "incomplete agent identity attributes")
    return AgentIdentity(
        subject=subject,
        employee_id=employee_id,
        odoo_employee_id=_attribute(attributes, "odoo_employee_id") or employee_id,
        vicidial_username=vicidial_username,
        role=_attribute(attributes, "role_template") or "codestra_agent",
        business_unit_id=_attribute(attributes, "business_unit_id") or "",
        tenant_id=_attribute(attributes, "tenant_id") or "",
    )

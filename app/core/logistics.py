"""Fail-closed logistics domain rules and route-level identity."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import Header, HTTPException

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator

ORDER_TRANSITIONS = {
    "DRAFT": {"QUOTE_PENDING", "CANCELLED"},
    "QUOTE_PENDING": {"QUOTED", "REJECTED", "CANCELLED"},
    "QUOTED": {"APPROVED", "REJECTED", "CANCELLED"},
    "APPROVED": {"BOOKED", "CANCELLED"},
    "BOOKED": set(),
    "CANCELLED": set(),
    "REJECTED": set(),
}
SHIPMENT_TRANSITIONS = {
    "CREATED": {"AWAITING_DISPATCH", "CANCELLED"},
    "AWAITING_DISPATCH": {"DISPATCHED", "ON_HOLD", "CANCELLED"},
    "DISPATCHED": {"DRIVER_ASSIGNED", "ON_HOLD", "CANCELLED"},
    "DRIVER_ASSIGNED": {"EN_ROUTE_TO_PICKUP", "ON_HOLD", "CANCELLED"},
    "EN_ROUTE_TO_PICKUP": {"ARRIVED_PICKUP", "DELIVERY_EXCEPTION", "ON_HOLD"},
    "ARRIVED_PICKUP": {"PICKED_UP", "DELIVERY_EXCEPTION"},
    "PICKED_UP": {"IN_TRANSIT", "DELIVERY_EXCEPTION"},
    "IN_TRANSIT": {"ARRIVED_DELIVERY", "DELIVERY_EXCEPTION", "ON_HOLD"},
    "ARRIVED_DELIVERY": {"DELIVERED", "DELIVERY_EXCEPTION"},
    "DELIVERED": {"CLOSED", "RETURN_REQUESTED"},
    "DELIVERY_EXCEPTION": {"IN_TRANSIT", "ON_HOLD", "RETURN_REQUESTED"},
    "ON_HOLD": {"AWAITING_DISPATCH", "IN_TRANSIT", "CANCELLED"},
    "RETURN_REQUESTED": {"RETURNED"},
    "RETURNED": {"CLOSED"},
    "CANCELLED": set(),
    "CLOSED": set(),
}

ROLE_PERMISSIONS = {
    "LOGISTICS_VIEWER": {"read"},
    "LOGISTICS_CUSTOMER": {"read", "create_order", "create_claim"},
    "LOGISTICS_DRIVER": {"read", "driver_status", "proof", "exception"},
    "LOGISTICS_DISPATCHER": {
        "read",
        "create_order",
        "create_shipment",
        "dispatch",
        "proof",
        "exception",
    },
    "LOGISTICS_MANAGER": {
        "read",
        "create_order",
        "create_shipment",
        "dispatch",
        "proof",
        "exception",
        "quote",
        "claim_review",
    },
}


@dataclass(frozen=True)
class LogisticsPrincipal:
    subject: str
    tenant_id: str
    workspace_id: str
    roles: frozenset[str]

    def require(self, permission: str) -> None:
        if not any(
            permission in ROLE_PERMISSIONS.get(role, set()) for role in self.roles
        ):
            raise HTTPException(403, "logistics permission denied")


def _bearer(value: str) -> str:
    scheme, sep, token = value.partition(" ")
    if scheme.lower() != "bearer" or not sep or not token.strip():
        raise HTTPException(401, "bearer authorization required")
    return token.strip()


async def logistics_principal(
    authorization: str = Header(..., alias="Authorization"),
) -> LogisticsPrincipal:
    try:
        claims = KeycloakValidator(
            issuer=settings.keycloak_issuer,
            audience=settings.keycloak_audience,
            jwks_url=settings.keycloak_jwks_url,
            authorized_parties=frozenset(
                x.strip()
                for x in settings.keycloak_authorized_parties.split(",")
                if x.strip()
            ),
        ).validate(_bearer(authorization))
    except (JWTAuthError, ValueError) as exc:
        raise HTTPException(401, "invalid logistics identity") from exc
    tenant = claims.get("tenant_id")
    workspace = claims.get("workspace_id")
    subject = claims.get("sub")
    roles = set(claims.get("roles", [])) | set(
        claims.get("realm_access", {}).get("roles", [])
    )
    if not all(isinstance(v, str) and v for v in (tenant, workspace, subject)):
        raise HTTPException(403, "tenant identity incomplete")
    allowed = frozenset(roles).intersection(ROLE_PERMISSIONS)
    if not allowed:
        raise HTTPException(403, "logistics role required")
    return LogisticsPrincipal(
        cast(str, subject), cast(str, tenant), cast(str, workspace), allowed
    )


def validate_transition(
    current: str, target: str, transitions: dict[str, set[str]]
) -> None:
    if target not in transitions.get(current, set()):
        raise HTTPException(409, f"invalid transition {current}->{target}")


def request_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_digest_match(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def utcnow() -> datetime:
    return datetime.now(UTC)

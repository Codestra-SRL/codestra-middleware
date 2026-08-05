from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header, HTTPException

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator

SUPERVISOR_ROLES = frozenset(
    {
        "CALL_CENTER_SUPERVISOR",
        "CALL_CENTER_MANAGER",
        "QA_REVIEWER",
        "QA_MANAGER",
        "COMPLIANCE_REVIEWER",
        "WORKFORCE_MANAGER",
        "CAMPAIGN_VIEWER",
        "CAMPAIGN_OPERATOR",
        "SUPERVISOR_AUDITOR",
    }
)


@dataclass(frozen=True)
class SupervisorPrincipal:
    subject: str
    tenant_id: str
    workspace_id: str
    roles: frozenset[str]
    team_ids: frozenset[str]
    campaign_ids: frozenset[str]

    def require(self, *roles: str) -> None:
        if not self.roles.intersection(roles):
            raise HTTPException(403, "supervisor permission denied")

    def authorize_team(self, team_id: str) -> None:
        if "CALL_CENTER_MANAGER" not in self.roles and team_id not in self.team_ids:
            raise HTTPException(404, "resource not found")


@lru_cache(maxsize=1)
def _validator() -> KeycloakValidator:
    return KeycloakValidator(
        issuer=settings.keycloak_issuer,
        audience=settings.keycloak_audience,
        jwks_url=settings.keycloak_jwks_url,
        authorized_parties=frozenset(
            value.strip()
            for value in settings.keycloak_authorized_parties.split(",")
            if value.strip()
        ),
    )


def require_supervisor(
    authorization: str = Header("", alias="Authorization"),
) -> SupervisorPrincipal:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "authenticated supervisor required")
    try:
        claims = _validator().validate(authorization.removeprefix("Bearer "))
    except JWTAuthError as exc:
        raise HTTPException(401, "supervisor token rejected") from exc
    roles = frozenset(claims.get("realm_access", {}).get("roles", ()))
    if not roles.intersection(SUPERVISOR_ROLES):
        raise HTTPException(403, "supervisor role required")
    tenant = claims.get("tenant_id")
    workspace = claims.get("workspace_id")
    teams = claims.get("supervisor_teams")
    if (
        not isinstance(tenant, str)
        or not isinstance(workspace, str)
        or not isinstance(teams, list)
    ):
        raise HTTPException(403, "supervisor scope claims required")
    return SupervisorPrincipal(
        subject=str(claims["sub"]),
        tenant_id=tenant,
        workspace_id=workspace,
        roles=roles,
        team_ids=frozenset(map(str, teams)),
        campaign_ids=frozenset(map(str, claims.get("campaigns", ()))),
    )

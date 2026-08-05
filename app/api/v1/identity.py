"""Enterprise IAM discovery endpoints backed by validated OIDC identity."""

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.iam import IAMAuthorizationError, IdentityContext, ROLE_PERMISSIONS
from app.core.jwt_auth import JWTAuthError, KeycloakValidator

router = APIRouter(prefix="/api/v1", tags=["enterprise-identity"])


def _identity(authorization: str) -> IdentityContext:
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise HTTPException(401, "bearer authorization required")
    try:
        claims = KeycloakValidator(
            issuer=settings.keycloak_issuer,
            audience=settings.keycloak_audience,
            jwks_url=settings.keycloak_jwks_url,
            authorized_parties=frozenset(
                item.strip() for item in settings.keycloak_authorized_parties.split(",") if item.strip()
            ),
        ).validate(token)
        return IdentityContext.from_validated_claims(claims)
    except (JWTAuthError, IAMAuthorizationError) as exc:
        raise HTTPException(401, "identity validation failed") from exc


@router.get("/auth/session")
def current_session(authorization: str = Header("", alias="Authorization")) -> dict[str, object]:
    identity = _identity(authorization)
    return {
        "subject": identity.subject,
        "tenant_id": identity.tenant_id,
        "workspace_id": identity.workspace_id,
        "roles": sorted(identity.roles),
        "permissions": sorted(identity.permissions),
        "session_id": identity.session_id,
    }


@router.get("/roles")
def list_roles(authorization: str = Header("", alias="Authorization")) -> dict[str, object]:
    identity = _identity(authorization)
    identity.require_permission("identity.read")
    return {"items": sorted(ROLE_PERMISSIONS)}


@router.get("/permissions")
def list_permissions(authorization: str = Header("", alias="Authorization")) -> dict[str, object]:
    identity = _identity(authorization)
    identity.require_permission("identity.read")
    permissions = sorted({item for values in ROLE_PERMISSIONS.values() for item in values})
    return {"items": permissions}

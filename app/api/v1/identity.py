"""Enterprise IAM discovery endpoints backed by validated OIDC identity."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.iam import IAMAuthorizationError, IdentityContext, ROLE_PERMISSIONS
from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from app.core.identity_provider import IdentityProviderError, KeycloakLifecycleClient
from app.db.session import get_session
from fastapi import Depends

router = APIRouter(prefix="/api/v1", tags=["enterprise-identity"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: SecretStr
    otp: SecretStr | None = None


class RefreshRequest(BaseModel):
    refresh_token: SecretStr


class ServiceAccountRequest(BaseModel):
    client_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
    display_name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(max_length=32)


class FederationProviderRequest(BaseModel):
    alias: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
    provider: Literal["saml", "oidc"]
    enabled: bool = False
    metadata_url: str = Field(pattern=r"^https://")


class UserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    email: str = Field(min_length=3, max_length=320)
    tenant_id: UUID
    workspace_id: UUID


class AccessReviewRequest(BaseModel):
    review_type: Literal["PERIODIC", "ROLE_CHANGE", "PRIVILEGED", "TERMINATION"]
    due_at: str


def _provider() -> KeycloakLifecycleClient:
    return KeycloakLifecycleClient(
        token_url=settings.keycloak_token_url,
        logout_url=settings.keycloak_logout_url,
        admin_base_url=settings.keycloak_admin_base_url,
        browser_client_id=settings.keycloak_browser_client_id,
        browser_client_secret_file=settings.keycloak_browser_client_secret_file,
        admin_client_id=settings.keycloak_admin_client_id,
        admin_client_secret_file=settings.keycloak_admin_client_secret_file,
    )


def _admin(authorization: str, permission: str) -> IdentityContext:
    identity = _identity(authorization)
    try:
        identity.require_permission(permission)
    except IAMAuthorizationError as exc:
        raise HTTPException(403, "identity administration denied") from exc
    return identity


@router.post("/auth/login")
async def login(body: LoginRequest) -> dict[str, object]:
    try:
        result = await _provider().login(
            body.username,
            body.password.get_secret_value(),
            body.otp.get_secret_value() if body.otp else None,
        )
    except IdentityProviderError as exc:
        raise HTTPException(401, "authentication failed") from exc
    return result


@router.post("/auth/mfa")
async def mfa(body: LoginRequest) -> dict[str, object]:
    if body.otp is None:
        raise HTTPException(422, "OTP required")
    return await login(body)


@router.post("/auth/refresh")
async def refresh(body: RefreshRequest) -> dict[str, object]:
    try:
        return await _provider().refresh(body.refresh_token.get_secret_value())
    except IdentityProviderError as exc:
        raise HTTPException(401, "refresh denied") from exc


@router.post("/auth/logout", status_code=204)
async def logout(body: RefreshRequest) -> None:
    try:
        await _provider().logout(body.refresh_token.get_secret_value())
    except IdentityProviderError as exc:
        raise HTTPException(401, "logout denied") from exc


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


@router.get("/users")
async def list_users(authorization: str = Header("", alias="Authorization")) -> dict[str, object]:
    _admin(authorization, "identity.read")
    try:
        result = await _provider().admin_request("GET", "/users?max=100")
    except IdentityProviderError as exc:
        raise HTTPException(503, "identity provider unavailable") from exc
    return {"items": result if isinstance(result, list) else []}


@router.post("/users", status_code=201)
async def create_user(
    body: UserRequest,
    authorization: str = Header("", alias="Authorization"),
) -> dict[str, str]:
    admin = _admin(authorization, "identity.write")
    try:
        admin.require_scope(str(body.tenant_id), str(body.workspace_id))
        await _provider().admin_request(
            "POST",
            "/users",
            payload={
                "username": body.username,
                "email": body.email,
                "enabled": False,
                "emailVerified": False,
                "requiredActions": ["VERIFY_EMAIL", "CONFIGURE_TOTP", "UPDATE_PASSWORD"],
                "attributes": {
                    "tenant_id": [str(body.tenant_id)],
                    "workspace_id": [str(body.workspace_id)],
                },
            },
        )
    except (IdentityProviderError, IAMAuthorizationError) as exc:
        raise HTTPException(403, "user creation denied") from exc
    return {"username": body.username, "status": "DISABLED_PENDING_VERIFICATION"}


@router.post("/users/{user_id}/sessions/revoke", status_code=204)
async def revoke_user_sessions(
    user_id: UUID,
    authorization: str = Header("", alias="Authorization"),
) -> None:
    _admin(authorization, "session.revoke")
    try:
        await _provider().admin_request("POST", f"/users/{user_id}/logout")
    except IdentityProviderError as exc:
        raise HTTPException(503, "session revocation failed") from exc


@router.post("/access-reviews", status_code=201)
async def create_access_review(
    body: AccessReviewRequest,
    authorization: str = Header("", alias="Authorization"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    admin = _admin(authorization, "policy.manage")
    review_id = uuid4()
    result = await db.execute(
        text("""
            INSERT INTO iam_access_review (
                id,tenant_id,workspace_id,review_type,status,due_at,
                created_by,updated_by,version,audit_id
            ) VALUES (
                :id,:tenant,:workspace,:review_type,'OPEN',CAST(:due_at AS timestamptz),
                :actor,:actor,1,:audit_id
            ) RETURNING id
        """),
        {
            "id": review_id,
            "tenant": UUID(admin.tenant_id),
            "workspace": UUID(admin.workspace_id),
            "review_type": body.review_type,
            "due_at": body.due_at,
            "actor": admin.subject,
            "audit_id": uuid4(),
        },
    )
    await db.commit()
    return {"id": str(result.scalar_one()), "status": "OPEN"}


@router.post("/service-accounts", status_code=201)
async def create_service_account(
    body: ServiceAccountRequest,
    authorization: str = Header("", alias="Authorization"),
) -> dict[str, str]:
    _admin(authorization, "identity.write")
    if any(not scope or len(scope) > 96 for scope in body.scopes):
        raise HTTPException(422, "service-account scope invalid")
    try:
        await _provider().admin_request(
            "POST",
            "/clients",
            payload={
                "clientId": body.client_id,
                "name": body.display_name,
                "enabled": False,
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "publicClient": False,
                "attributes": {"codestra.requested_scopes": " ".join(sorted(set(body.scopes)))},
            },
        )
    except IdentityProviderError as exc:
        raise HTTPException(503, "service-account creation failed") from exc
    return {"client_id": body.client_id, "status": "DISABLED_PENDING_SCOPE_APPROVAL"}


@router.post("/identity-providers", status_code=201)
async def create_identity_provider(
    body: FederationProviderRequest,
    authorization: str = Header("", alias="Authorization"),
) -> dict[str, str]:
    _admin(authorization, "policy.manage")
    try:
        await _provider().admin_request(
            "POST",
            "/identity-provider/instances",
            payload={
                "alias": body.alias,
                "providerId": body.provider,
                "enabled": False,
                "trustEmail": False,
                "storeToken": False,
                "linkOnly": True,
                "config": {"metadataDescriptorUrl": body.metadata_url},
            },
        )
    except IdentityProviderError as exc:
        raise HTTPException(503, "identity-provider configuration failed") from exc
    return {"alias": body.alias, "status": "DISABLED_PENDING_SECURITY_REVIEW"}

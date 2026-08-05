# Enterprise IAM architecture

Codestra uses the configured OIDC identity provider as the authentication
authority and middleware as the authorization enforcement point. Middleware
does not store passwords, OTP seeds, recovery codes, hardware-key material, or
refresh tokens.

## Trust boundary

Only cryptographically validated token claims may establish a subject, tenant,
workspace, department, role, permission, or session. Request headers and body
fields never establish identity. Tokens require the configured issuer,
audience, signature, expiry, issued-at time, and authorized party.

`IdentityContext` is immutable after validation. Resource handlers must call
both `require_scope` and `require_permission`; a role alone is not a resource
scope. Unknown roles and incomplete claims fail closed.

## Roles and permissions

The platform role catalogue is centralized in `app/core/iam.py`. Roles expand
to the smallest default permission set. Platform-owner wildcard authority is
reserved for break-glass governance and must be MFA-protected and audited by
the identity provider. AI employees receive read-only memory and knowledge
permissions by default and no tool, workflow, financial, telephony, or delete
authority.

## Sessions and MFA

Keycloak remains responsible for login, magic-link/OTP flows, TOTP and WebAuthn,
session rotation, refresh-token rotation, device history, lockout, recovery,
and revocation. Middleware exposes only validated session metadata. A later
provider configuration PR must prove MFA policies and session limits in the
deployed realm before Section 3 can pass production acceptance.

## API boundary

- `GET /api/v1/auth/session`
- `GET /api/v1/roles`
- `GET /api/v1/permissions`

Password login, logout, refresh, MFA mutation, user administration, and service
account creation are intentionally not reimplemented until their provider-side
contracts and durable audit migrations are reviewed. They must not be simulated
with local credentials.

## Exit gates

Section 3 requires deployed-provider authentication and MFA evidence, tenant
and workspace integration tests against PostgreSQL-backed resources, session
revocation tests, complete audit persistence, and performance validation. The
current PR is a reviewable foundation and must remain draft until those gates
are supplied.

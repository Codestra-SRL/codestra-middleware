# Phase 3A provider authentication

## Postly

The deployed Postiz public API authenticates organization API keys and organization
OAuth tokens. It has no least-privilege machine-token model; an API key is treated as
organization superadmin. The existing organization credential is installed only in
the Middleware staging secret directory as `postiz_api_key`, owned by UID/GID 10001
with mode `0400`.

Private authentication validation returned `200` for the credential and `401` for
invalid and missing credentials. Middleware adapter health returned `AVAILABLE` and
account discovery returned an empty, valid list. No API write or social post occurred.
The private path is `10.40.0.1` to `10.40.0.3` on VLAN 4001 with MTU 1400. ICMP at
the configured MTU, TCP 443, and TLS verification for `social.codestra.co` pass. The
public route was not changed. The public API is not source-restricted, so private-only
source enforcement is a known limitation rather than a claimed control.

## Hootsuite external action

An operator with an approved Hootsuite developer account must create:

- application name: `Codestra Social Staging`;
- redirect URI: `https://middleware.codestra.co/api/v1/social/oauth/hootsuite/callback`;
- grant: OAuth 2 authorization code;
- scopes: `offline` initially, which is required for refresh tokens; add
  `analytics:read` only when analytics access is separately approved;
- client ID file: `/etc/codestra/secrets/middleware-staging/social/hootsuite_client_id`;
- client secret file: `/etc/codestra/secrets/middleware-staging/social/hootsuite_client_secret`;
- state secret file: `/etc/codestra/secrets/middleware-staging/social/hootsuite_oauth_state_secret`;
- token file: `/etc/codestra/secrets/middleware-staging/social/hootsuite_token.json`.

No Hootsuite credential was found or fabricated. Real OAuth and provider canary remain
blocked on this external account action and a positively classified staging account.
The callback URI above is the expected registration value; the public callback route
must remain inactive until the client credentials, state secret, durable state ledger,
and controlled staging deployment are all present. Hootsuite documents the authorize
and token requirements in its
[official REST API reference](https://apidocs.hootsuite.com/docs/api/index.html).

## Certification state

- Phase 2 PR: draft, head `3f38ffcd761696475fe910fcc07c11c6e3dc4d86`, exact-SHA CI passed.
- Phase 3 baseline: draft PR #182 at `a668ba094d02891a7bcb22bb8d62536bfa46392a`, exact-SHA CI passed before this Phase 3A update.
- Postly authentication and read-only account discovery: passed.
- Postly account inventory: zero staging-safe, zero production, zero unknown accounts.
- Postly write/schedule/cancel canary: blocked because no staging-safe account exists.
- Hootsuite developer app, real OAuth, refresh, discovery, and canary: blocked on an approved external developer account and staging-safe profile.
- Durable OAuth state: implemented and validated with PostgreSQL migration round-trip and restart/concurrency tests.
- Full Python 3.12 suite: 841 passed.
- Changed-file secret scan, Bandit, dependency integrity, and Trivy HIGH/CRITICAL scan: passed.
- Production social posts and production Odoo writes: zero.

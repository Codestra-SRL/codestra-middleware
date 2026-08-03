# Postly integration security model

Trust boundaries: browsers reach public Caddy; Middleware reaches a future private adapter; n8n reaches Middleware only. There is no direct Middleware/n8n database, Redis, Temporal, Elasticsearch, Docker, or media-volume access.

The installed API credential is organization-scoped and effectively superadmin within that organization; it is not a least-privilege user token. Therefore no production service credential was generated. Activation requires a dedicated Codestra organization API credential stored on the Middleware host secret manager, referenced as `POSTLY_API_KEY`, with only a SHA-256 fingerprint recorded. Never log request authorization, captions, media bytes, provider tokens, or personal data.

Rotation: create/rotate through the documented organization-admin UI/API, atomically update the Middleware secret reference, verify read-only `/integrations`, revoke the old credential, and record actor/time/fingerprints. Emergency revocation rotates immediately and disables the adapter route. Because rotation invalidates the organization key, coordinate all consumers.

Private listener design: internal DNS name after vSwitch provisioning; TLS with an internal CA or mutually authenticated proxy; source allowlist for the verified Middleware private IP; 10 requests/s baseline with burst 20 subject to load testing; upload-specific 100 MiB ceiling or the stricter provider limit; 10-second metadata and 120-second upload timeouts; forward validated `X-Correlation-ID`; redact bodies and authorization headers.

Current blocker: this host has no `10.40.0.x` address or route, and the Middleware private address is unverified. Public fallback is not activated.

# Exact Middleware-server changes required

1. Configure the verified vSwitch address/route; provide its confirmed private source IP to the Postly firewall/adapter allowlist.
2. Implement this OpenAPI contract and validate all JSON schemas at ingress/egress.
3. Store the Postly organization API key in the approved server-side secret manager; record only its reference and fingerprint.
4. Implement atomic idempotency claims using the documented composite key and persist Postly group/post IDs.
5. Enforce approval and lifecycle transitions before any Postly write.
6. Proxy media after scanning/validation; do not give n8n the Postly credential.
7. Implement bounded retry plus reconciliation; treat uncertain writes as reconciliation-required.
8. Expose `POST /api/v1/social/provider-events` only after HMAC, timestamp, replay cache, schema validation, TLS, and source controls are complete.
9. Emit privacy-safe integration/backlog metrics and configure a real alert receiver/recovery test.
10. Register production and staging n8n webhook paths separately and validate n8n outputs against the handoff schemas.

No Middleware or n8n changes were made from this server.

# Postly staging authentication

No approved staging Postly API credential or webhook secret was available. The reachable deployed runtime authenticates its public API with an organization API key, but the only known identity is production-scoped and was not copied, rotated, or used. Native outward webhook delivery is unsigned, which does not satisfy the Middleware ingress contract.

Staging must use a dedicated `postly-social-01` identity. Store API and webhook secrets in root-owned runtime files such as `/run/secrets/...`; never commit values or place them in repository `.env` files. Prefer private mTLS plus the provider-supported API key, with timestamp/nonce/HMAC protection where Codestra controls both endpoints.

Credential-dependent validation remains blocked until a least-privilege staging identity and a signed outbound webhook mechanism are available.

# Postly staging authentication

No approved Postly API credential or webhook secret was discoverable on Middleware Server A, and the Postly server was inaccessible. No credential was generated or rotated.

Staging must use a dedicated `postly-social-01` identity. Store API and webhook secrets in root-owned runtime files such as `/run/secrets/...`; never commit values or place them in repository `.env` files. Prefer private mTLS plus the provider-supported API key, with timestamp/nonce/HMAC protection where Codestra controls both endpoints.

Credential-dependent validation remains blocked until server access and an approved staging credential are available.

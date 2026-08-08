# Hootsuite authentication

Official OAuth endpoints are `https://platform.hootsuite.com/oauth2/auth` and `/oauth2/token`. Codestra uses authorization code plus `offline` scope, mandatory signed state, HTTP Basic client authentication for exchange/refresh, and a root-mounted mode-0600 token file.

OAuth state is persisted hash-only in PostgreSQL with tenant, nonce hash, issue/expiry,
status, and consumption timestamps. Consumption is an atomic conditional update, so
replay is rejected across workers and restarts.

Required files are `HOOTSUITE_CLIENT_ID_FILE`, `HOOTSUITE_CLIENT_SECRET_FILE`, `HOOTSUITE_OAUTH_STATE_SECRET_FILE`, and `HOOTSUITE_TOKEN_FILE`. No approved developer app or credentials were present during Phase 3; real OAuth remains blocked.

The expected callback is
`https://middleware.codestra.co/api/v1/social/oauth/hootsuite/callback`. The route is
implemented and fails closed when credentials, state persistence, or token storage
are unavailable. External activation still requires approved credentials and a
separately controlled staging deployment.

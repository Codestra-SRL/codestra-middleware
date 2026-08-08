# Hootsuite authentication

Official OAuth endpoints are `https://platform.hootsuite.com/oauth2/auth` and `/oauth2/token`. Codestra uses authorization code plus `offline` scope, mandatory signed state, HTTP Basic client authentication for exchange/refresh, and a root-mounted mode-0600 token file.

Required files are `HOOTSUITE_CLIENT_ID_FILE`, `HOOTSUITE_CLIENT_SECRET_FILE`, `HOOTSUITE_OAUTH_STATE_SECRET_FILE`, and `HOOTSUITE_TOKEN_FILE`. No approved developer app or credentials were present during Phase 3; real OAuth remains blocked.

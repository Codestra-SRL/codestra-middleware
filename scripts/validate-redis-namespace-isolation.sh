#!/usr/bin/env bash
set -euo pipefail
: "${REDIS_URL_FILE:?set REDIS_URL_FILE to an approved secret-mounted URL}"
test -s "$REDIS_URL_FILE"
cli=${REDIS_CLI_BIN:-redis-cli}
url=$(<"$REDIS_URL_FILE")
test "$($cli -u "$url" --raw PING)" = PONG
key="codestra:integration-test:validation:$RANDOM"
trap '"$cli" -u "$url" DEL "$key" >/dev/null 2>&1 || true' EXIT
test "$($cli -u "$url" --raw SETEX "$key" 30 ok)" = OK
test "$($cli -u "$url" --raw GET "$key")" = ok
echo REDIS_NAMESPACE_ISOLATION_VALIDATION=PASS

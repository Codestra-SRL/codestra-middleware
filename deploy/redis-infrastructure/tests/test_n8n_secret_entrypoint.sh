#!/usr/bin/env bash
set -euo pipefail
base=$(cd "$(dirname "$0")/.." && pwd)
main="$base/scripts/redis-secret-entrypoint.sh"
helper="$base/scripts/n8n-node-entrypoint"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
capture="$tmp/docker-entrypoint.sh"
# shellcheck disable=SC2016
printf '#!/bin/sh\n: > %q\nfor arg do printf "%%s\\0" "$arg" >> %q; done\n' "$tmp/argv" "$tmp/argv" > "$capture"
chmod 0755 "$capture"
grep -Fq 'exec su -p node -s /usr/local/bin/n8n-node-entrypoint -- "$@"' "$main"
grep -Fq 'exec /docker-entrypoint.sh "$@"' "$helper"
if grep -Eq '\$\*|eval|/bin/sh -c.*docker-entrypoint' "$main" "$helper"; then exit 1; fi
test_helper="$tmp/n8n-node-entrypoint"
sed "s#/docker-entrypoint.sh#$capture#g" "$helper" > "$test_helper"
chmod 0755 "$test_helper"
python3 - "$test_helper" "$tmp/argv" <<'PY'
import subprocess, sys
helper, capture = sys.argv[1:]
cases = [[], ['n8n'], ['worker'], ['worker', '--concurrency=5'], ['worker', '--concurrency', '5'], ['webhook'], ['n8n', 'start'], ['space value', 'quote"value', "single'quote", 'semi;colon', '$(touch SHOULD_NOT_EXIST)', '--leading', '', 'tail']]
for args in cases:
    subprocess.run([helper, '--', *args], check=True)
    got = open(capture, 'rb').read().split(b'\0')[:-1]
    if got != [a.encode() for a in args]: raise SystemExit('argument mismatch')
print('N8N_ENTRYPOINT_NO_ARGUMENT_GATE=PASS')
print('N8N_ENTRYPOINT_SINGLE_ARGUMENT_GATE=PASS')
print('N8N_ENTRYPOINT_MULTI_ARGUMENT_GATE=PASS')
print('N8N_ENTRYPOINT_CONCURRENCY_FLAG_GATE=PASS')
print('N8N_ENTRYPOINT_SPACE_PRESERVATION_GATE=PASS')
print('N8N_ENTRYPOINT_QUOTE_PRESERVATION_GATE=PASS')
print('N8N_ENTRYPOINT_SHELL_INJECTION_GATE=PASS_EXPECTED_NO_EXECUTION')
PY
test ! -e SHOULD_NOT_EXIST
echo N8N_RUNTIME_USER_CONTRACT=PASS
echo N8N_SECRET_OUTPUT=0

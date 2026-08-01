#!/usr/bin/env bash
set -euo pipefail

: "${STAGING_SECRET_DIRECTORY:?required}"
"$(dirname "$0")/validate-secret-permissions.sh" >/dev/null
image="${POSTGRES_IMAGE:?exact digest required}"
case "${image}" in *@sha256:????????????????????????????????????????????????????????????????) ;; *) exit 1 ;; esac

suffix="${GITHUB_RUN_ID:-local}-$$"
containers=()
cleanup() {
  for container in "${containers[@]}"; do
    docker stop "${container}" >/dev/null 2>&1 || true
    docker rm "${container}" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

for name in middleware-postgres-password odoo-postgres-password redis-password middleware-database-url redis-url lead-automation-hmac-v2 n8n-encryption-key; do
  container="lead-secret-probe-${suffix}-${name}"
  containers+=("${container}")
  docker create --name "${container}" --network none --read-only --user 0:0 \
    --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
    --cap-add SETGID --cap-add SETUID \
    --security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,nodev,size=8m \
    --mount "type=bind,src=${STAGING_SECRET_DIRECTORY}/${name},dst=/run/secrets/${name},readonly" \
    --entrypoint sh "${image}" -ec \
    "test -f /run/secrets/${name}; install -d -m 0700 /tmp/runtime; install -m 0400 -o 65534 -g 65534 /run/secrets/${name} /tmp/runtime/value; chown 65534:65534 /tmp/runtime; exec gosu nobody sh -ec 'test -s /tmp/runtime/value; test ! -w /run/secrets/${name}; test ! -w /tmp/runtime/value'" >/dev/null
  test -z "$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container}" | grep -E 'synthetic-test-only|synthetic-secret-probe' || true)"
  docker start -a "${container}" >/dev/null
  test "$(docker inspect -f '{{.State.ExitCode}}' "${container}")" = 0
  test -z "$(docker logs "${container}" 2>&1)"
done

echo CONTAINER_SECRET_READ_ONLY_GATE=PASS
echo CONTAINER_SECRET_ENVIRONMENT_LEAK_GATE=PASS
echo CONTAINER_SECRET_LOG_LEAK_GATE=PASS
echo CONTAINER_SECRET_TARGET_GATE=PASS

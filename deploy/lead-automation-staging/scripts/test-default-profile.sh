#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
compose="${root}/compose.yaml"
project="lead-default-profile-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
secret_dir="$(mktemp -d)"
chmod 700 "${secret_dir}"
for name in \
  middleware-postgres-password \
  odoo-postgres-password \
  redis-password \
  middleware-database-url \
  redis-url \
  lead-automation-hmac-v2 \
  n8n-encryption-key; do
  printf 'synthetic-profile-test-only\n' > "${secret_dir}/${name}"
  chmod 400 "${secret_dir}/${name}"
done
export STAGING_SECRET_DIRECTORY="${secret_dir}"

cleanup() {
  docker compose --project-name "${project}" -f "${compose}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  find "${secret_dir}" -type f -delete
  rmdir "${secret_dir}"
}
trap cleanup EXIT

docker compose --project-name "${project}" -f "${compose}" config >/dev/null
profiles="$(docker compose --project-name "${project}" -f "${compose}" config --profiles)"
grep -qx deployment <<<"${profiles}"
grep -qx operations <<<"${profiles}"
test -z "$(docker ps -aq --filter "label=com.docker.compose.project=${project}")"
docker compose --project-name "${project}" -f "${compose}" up --no-start >/dev/null
created="$(docker compose --project-name "${project}" -f "${compose}" ps -a --services)"
for forbidden in middleware-migrate middleware odoo n8n backup-verify; do
  ! grep -qx "${forbidden}" <<<"${created}"
done
cleanup
trap - EXIT
test -z "$(docker ps -aq --filter "label=com.docker.compose.project=${project}")"
echo DEFAULT_PROFILE_NON_CREATION_GATE=PASS

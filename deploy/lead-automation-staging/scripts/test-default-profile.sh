#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
compose="${root}/compose.yaml"
project="lead-default-profile-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"

cleanup() {
  docker compose --project-name "${project}" -f "${compose}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose --project-name "${project}" -f "${compose}" config >/dev/null
profiles="$(docker compose --project-name "${project}" -f "${compose}" config --profiles)"
grep -qx deployment <<<"${profiles}"
grep -qx operations <<<"${profiles}"
docker compose --project-name "${project}" -f "${compose}" up --no-start >/dev/null
created="$(docker compose --project-name "${project}" -f "${compose}" ps -a --services)"
for forbidden in middleware-migrate middleware odoo n8n backup-verify; do
  ! grep -qx "${forbidden}" <<<"${created}"
done
echo DEFAULT_PROFILE_NON_CREATION_GATE=PASS

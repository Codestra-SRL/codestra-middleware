#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
compose="${root}/compose.yaml"
project="lead-default-profile-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"

docker compose --project-name "${project}" -f "${compose}" config >/dev/null
profiles="$(docker compose --project-name "${project}" -f "${compose}" config --profiles)"
grep -qx deployment <<<"${profiles}"
grep -qx operations <<<"${profiles}"
test -z "$(docker ps -aq --filter "label=com.docker.compose.project=${project}")"
created="$(docker compose --project-name "${project}" -f "${compose}" config --services)"
for forbidden in middleware-migrate middleware odoo n8n backup-verify; do
  ! grep -qx "${forbidden}" <<<"${created}"
done
test -z "$(docker ps -aq --filter "label=com.docker.compose.project=${project}")"
echo DEFAULT_PROFILE_NON_CREATION_GATE=PASS

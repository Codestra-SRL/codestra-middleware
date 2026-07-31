#!/usr/bin/env bash
set -euo pipefail

test -f Dockerfile
source_sha="$(git rev-parse HEAD)"
build_timestamp="1970-01-01T00:00:00Z"
first="codestra-security-repro:first"
second="codestra-security-repro:second"
cleanup() {
  docker image rm -f "${first}" "${second}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build --build-arg VCS_REF="${source_sha}" --build-arg SOURCE_SHA="${source_sha}" \
  --build-arg BUILD_REVISION="${source_sha}" --build-arg BUILD_TIMESTAMP="${build_timestamp}" \
  --tag "${first}" .
docker build --build-arg VCS_REF="${source_sha}" --build-arg SOURCE_SHA="${source_sha}" \
  --build-arg BUILD_REVISION="${source_sha}" --build-arg BUILD_TIMESTAMP="${build_timestamp}" \
  --tag "${second}" .

first_id="$(docker image inspect --format '{{.Id}}' "${first}")"
second_id="$(docker image inspect --format '{{.Id}}' "${second}")"
test "${first_id}" = "${second_id}"
printf 'BUILD_1_DIGEST=%s\nBUILD_2_DIGEST=%s\nIMAGE_REPRODUCIBILITY_GATE=PASS\n' \
  "${first_id}" "${second_id}"

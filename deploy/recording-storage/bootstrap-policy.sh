#!/bin/sh
set -eu

test "${RECORDING_DEPLOYMENT_ENVIRONMENT:-}" = 'staging'
test "${RECORDING_ENCRYPTION_MODE:-}" = 'SSE_S3'

bucket='codestra-recordings'
mc mb --with-lock --ignore-existing "recording/${bucket}"
mc version enable "recording/${bucket}"
mc encrypt set sse-s3 "recording/${bucket}"
mc encrypt info "recording/${bucket}" | grep -F 'SSE-S3'
mc retention set --default GOVERNANCE 365d "recording/${bucket}"

for identity in recording-middleware-write recording-middleware-read \
  recording-retention-worker recording-backup-auditor; do
  test -n "$identity"
done

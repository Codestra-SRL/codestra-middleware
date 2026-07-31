#!/bin/sh
set -eu

bucket='codestra-recordings'
mc mb --with-lock --ignore-existing "recording/${bucket}"
mc version enable "recording/${bucket}"
mc retention set --default GOVERNANCE 365d "recording/${bucket}"

for identity in recording-middleware-write recording-middleware-read \
  recording-retention-worker recording-backup-auditor; do
  test -n "$identity"
done

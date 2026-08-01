#!/usr/bin/env bash
set -euo pipefail

: "${STAGING_SECRET_DIRECTORY:?required}"
case "${STAGING_SECRET_DIRECTORY}" in /*) ;; *) echo "secret directory must be absolute" >&2; exit 1;; esac
test -d "${STAGING_SECRET_DIRECTORY}"
test ! -L "${STAGING_SECRET_DIRECTORY}"
test "$(stat -c '%a' "${STAGING_SECRET_DIRECTORY}")" = 700
owner="$(stat -c '%u' "${STAGING_SECRET_DIRECTORY}")"
test "${owner}" = 0
root="$(realpath -e "${STAGING_SECRET_DIRECTORY}")"

files=(middleware-postgres-password odoo-postgres-password redis-password middleware-database-url redis-url lead-automation-hmac-v2 n8n-encryption-key)
for name in "${files[@]}"; do
  path="${STAGING_SECRET_DIRECTORY}/${name}"
  test -f "${path}"
  test ! -L "${path}"
  test "$(stat -c '%h' "${path}")" = 1
  mode="$(stat -c '%a' "${path}")"
  test "${mode}" = 400
  owner="$(stat -c '%u' "${path}")"
  test "${owner}" = 0
  test -s "${path}"
  resolved="$(realpath -e "${path}")"
  case "${resolved}" in "${root}"/*) ;; *) echo "secret escaped approved directory" >&2; exit 1;; esac
done
echo HOST_SECRET_PERMISSION_GATE=PASS
echo HOST_SECRET_PATH_CONTAINMENT_GATE=PASS
echo HOST_SECRET_DIRECTORY_GATE=PASS
echo HOST_SECRET_FILE_MODE_GATE=PASS
echo HOST_SECRET_FILE_OWNER_GATE=PASS
echo HOST_SECRET_SYMLINK_REJECTION_GATE=PASS
echo HOST_SECRET_VALUE_DISCLOSURE_COUNT=0

#!/usr/bin/env bash
set -euo pipefail
validator="$(cd "$(dirname "$0")/.." && pwd)/scripts/validate-secret-permissions.sh"
tmp="$(mktemp -d)"
cleanup() { chmod -R u+rwX "${tmp}" 2>/dev/null || true; rm -rf -- "${tmp}"; }
trap cleanup EXIT
chmod 700 "${tmp}"
for name in middleware-postgres-password odoo-postgres-password redis-password middleware-database-url redis-url lead-automation-hmac-v2 n8n-encryption-key; do
  printf synthetic-test-only > "${tmp}/${name}"
  chmod 600 "${tmp}/${name}"
done
STAGING_SECRET_DIRECTORY="${tmp}" "${validator}" >/dev/null
chmod 644 "${tmp}/redis-password"
if STAGING_SECRET_DIRECTORY="${tmp}" "${validator}" >/dev/null 2>&1; then exit 1; fi
chmod 600 "${tmp}/redis-password"
ln -s redis-password "${tmp}/bad-link"
mv "${tmp}/n8n-encryption-key" "${tmp}/n8n-real"
ln -s n8n-real "${tmp}/n8n-encryption-key"
if STAGING_SECRET_DIRECTORY="${tmp}" "${validator}" >/dev/null 2>&1; then exit 1; fi
echo SECRET_PERMISSION_GATE=PASS

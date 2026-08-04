#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
exec bash "$root/deploy/redis-infrastructure/tests/test_n8n_secret_entrypoint.sh" "$@"

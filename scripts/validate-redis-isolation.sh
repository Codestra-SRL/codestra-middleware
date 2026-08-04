#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/validate-redis-namespace-isolation.sh" "$@"

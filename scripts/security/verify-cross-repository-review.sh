#!/usr/bin/env bash
set -euo pipefail

python scripts/security/evaluate-cross-repository-review.py \
  --decision "${1:?canonical decision path required}" \
  --bundle "${2:?Sigstore bundle path required}"

#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
policy="${root}/security/image-verification-policy.json"
decision="${root}/security/image-security-decision.json"
command -v cosign >/dev/null
jq -e . "${policy}" >/dev/null

decision_status="$(jq -r .status "${decision}")"
pending=0
while IFS=$'\t' read -r name digest method identity issuer; do
  case "${name}" in
    middleware) reference="docker.io/codestra/lead-staging-middleware@${digest}" ;;
    postgres|redis|odoo) reference="docker.io/library/${name}@${digest}" ;;
    n8n) reference="docker.io/n8nio/n8n@${digest}" ;;
    *) echo "UNKNOWN_IMAGE=${name}" >&2; exit 1 ;;
  esac
  if cosign verify --certificate-identity-regexp='.*' --certificate-oidc-issuer-regexp='.*' "${reference}" >/dev/null 2>&1; then
    echo "IMAGE_SIGNATURE_${name}=PASS"
    continue
  fi
  echo "IMAGE_SIGNATURE_${name}=NOT_AVAILABLE"
  if [[ "${name}" == middleware ]]; then
    echo CODESTRA_IMAGE_COSIGN_GATE=PENDING
    pending=1
  elif [[ "${method}" == digest_pin_plus_sbom_and_approved_risk_acceptance ]]; then
    echo "UPSTREAM_COSIGN_${name}=NOT_AVAILABLE_WITH_ALTERNATE_CONTROLS"
  else
    pending=1
  fi
done < <(jq -r '.images[] | [.image_name,.image_digest,.verification_method,(.cosign_certificate_identity//""),(.cosign_oidc_issuer//"")] | @tsv' "${policy}")

if [[ "${decision_status}" == approved_for_staging ]]; then
  python3 "${root}/security_decision.py"
  : "${SECURITY_APPROVAL_RECORD:?immutable external approval record required}"
  : "${PR_HEAD:?exact PR head required}"
  python3 - "${root}" "${SECURITY_APPROVAL_RECORD}" "${PR_HEAD}" <<'PY'
import datetime as dt
import importlib.util
import json
import pathlib
import sys

root, record_path, head = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
spec = importlib.util.spec_from_file_location("security_decision", root / "security_decision.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
decision = json.loads((root / "security/image-security-decision.json").read_text())
record = json.loads(record_path.read_text())
errors = module.validate_external(record, decision, head, dt.datetime.now(dt.timezone.utc))
if errors:
    raise SystemExit("\n".join(errors))
print("SECURITY_DECISION_EXTERNAL_APPROVAL_SEPARATION_GATE=PASS")
PY
else
  echo SECURITY_OWNER_ACCEPTANCE_GATE=PENDING
  pending=1
fi

if (( pending )); then
  echo IMAGE_SIGNATURE_AND_ACCEPTANCE_GATE=PENDING
  exit 3
fi
echo IMAGE_SIGNATURE_AND_ACCEPTANCE_GATE=PASS

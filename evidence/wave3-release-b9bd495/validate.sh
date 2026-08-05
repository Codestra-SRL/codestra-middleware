#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
sha256sum -c SHA256SUMS

for document in *.json; do
  jq -e . "${document}" >/dev/null
done

jq -e '
  .subject[0].digest.sha256 ==
    "9417dc4d6b489e157580d746e8edda66678f5c7cf8beb5a565f73f6ded654215" and
  .predicate.buildDefinition.externalParameters.source_commit ==
    "b9bd495ef65272463803b721698e5645316959cc"
' provenance.json >/dev/null

jq -e '
  (.statements | length) == 10 and
  all(.statements[];
    .status == "under_investigation" and
    all(.products[];
      .["@id"] | contains(
        "sha256%3A9417dc4d6b489e157580d746e8edda66678f5c7cf8beb5a565f73f6ded654215"
      )
    )
  )
' openvex.json >/dev/null

jq -e '
  .release.cosign_signature == "BLOCKED" and
  .controls.odoo_delivery_enabled == false and
  .controls.production_changes == "NONE" and
  .controls.real_odoo_write_count == 0
' release-evidence-report.json >/dev/null

jq -e '
  .staging_schema_approval.status == "BLOCKED" and
  .staging_credentials.status == "BLOCKED" and
  .odoo_delivery_enabled == false and
  .real_odoo_write_count == 0
' odoo-staging-validation.json >/dev/null

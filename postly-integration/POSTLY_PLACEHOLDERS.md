# Values still requiring authoritative input

- Postly and Middleware vSwitch IP addresses, subnet/prefix, gateway/route, and permitted private TCP port.
- Internal DNS hostname and internal TLS/mTLS CA/certificate ownership.
- Production secret-manager path for the organization API key and the resulting non-secret fingerprint.
- Middleware datastore/table names for idempotency, audit, and reconciliation.
- Registered production and staging n8n webhook paths and their authentication references.
- Alertmanager receiver and escalation contacts.
- Off-server Restic destination and retention approval.
- Controlled-canary social account/integration, provider OAuth credentials, approvers, content, schedule, and rollback authority.
- Final product display name (`Codestra Social` versus `Postly`) and authoritative high-resolution logo/source publication URL.

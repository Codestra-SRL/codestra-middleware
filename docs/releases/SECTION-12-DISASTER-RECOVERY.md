# Disaster recovery validation

Recovery evidence includes an off-system backup reference, checksum,
restore-test reference, measured RPO/RTO, service validation, data-integrity
check, owner, and timestamp. Restoration is tested in isolation and never
overwrites production during certification.

Manual failover remains disabled until a separate production governance
decision. Recovery plans cover PostgreSQL, Redis, n8n/workflows, configuration,
secrets metadata, monitoring, and reverse-proxy configuration.

# Lead operations

Operations APIs are tenant-scoped and RBAC protected. Permissions include `lead.read`, `lead.write`, `lead.score`, `lead.approve`, `identity.read`, `identity.merge`, `identity.review`, `attribution.read`, `revenue.read`, `revenue.write`, and `ops.leads`; none are granted automatically.

Dashboards use aggregate, low-cardinality metrics. Alerts cover identity conflicts, dedupe anomalies, DNC policy risk, stale attribution, and next-action failures. Logs and metrics must not contain full email, telephone, message text, tokens, or external identifiers.

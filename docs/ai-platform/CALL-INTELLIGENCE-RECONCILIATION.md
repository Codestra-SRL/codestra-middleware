# Reconciliation

The reconciler scans missing jobs, recordings, transcripts, analyses, QA, unknown Odoo results, duplicate callbacks and expired processing leases. It uses the canonical external key and per-stage uniqueness constraints, never creates a second transcript/analysis/QA/activity, and routes ambiguous writes to readback before retry.


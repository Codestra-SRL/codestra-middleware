# Production readiness and certification

Certification is an evidence review, not a deployment command. The release
manager submits a production-targeted evidence record with a deployment
strategy, distinct owners, backup/restore references, rollback rehearsal,
disaster-recovery evidence, maintenance notice, feature-flag snapshot, and all
mandatory gate results.

The API returns `CERTIFIED_FOR_CONTROLLED_PLANNING`. It cannot return an
activation authorization. Production activation requires a separate signed
governance decision after this package is reviewed.

The production readiness endpoint is read-only except for submitting evidence;
rollback and DR endpoints validate evidence only.

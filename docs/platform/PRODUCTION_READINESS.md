# Production readiness

N5 is staging foundation code, not broad production authorization. Before activation require exact-SHA CI, independent review, immutable images, SBOM/signature, disposable migration round-trip, synthetic end-to-end testing, backups, rollback, monitored staging stability, workflow drift baseline and security-owner approval.

Source defaults remain: social publish OFF, canary OFF, Odoo writes OFF, Hootsuite OFF, automatic AI publish OFF, automatic campaign approval OFF, provider failover OFF, dual publish OFF and dead-letter automatic replay OFF. External provider account connection remains a separate prerequisite.

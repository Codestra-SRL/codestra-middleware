# Stage gates

Each stage transitions `PLANNED → AWAITING_APPROVAL → APPROVED → PRECHECK_RUNNING → READY → ACTIVE → OBSERVING → COMPLETED`. A failed precheck blocks the stage; dangerous observations fail and roll back; degraded observations pause. Every transition and observation is audited.

Required evidence includes limits, approval reference, observation window, health, error rate, latency, queue depth, retries, reconciliation, duplicate counts, unauthorized writes, tenant isolation, capacity and dependent-service health.

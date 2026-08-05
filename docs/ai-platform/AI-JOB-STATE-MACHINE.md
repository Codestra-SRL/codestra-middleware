# AI job state machine

Jobs move through `RECEIVED`, `VALIDATING`, `VALIDATED`, `APPROVAL_REQUIRED`, `APPROVED`, `QUEUED`, `RUNNING`, `RESULT_VALIDATION`, `COMPLETED`, `RETRY_SCHEDULED`, `FAILED`, `REJECTED`, `CANCELLED`, and `UNKNOWN`. State changes are audited; terminal states cannot be overwritten by callbacks.

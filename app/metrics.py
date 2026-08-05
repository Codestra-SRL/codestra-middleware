from prometheus_client import Counter, Gauge, Histogram

ACK = Histogram("codestra_fast_ack_seconds", "Fast ACK total latency")
DB_COMMIT = Histogram("codestra_db_commit_seconds", "Ingress commit latency")
AUTH_FAILURES = Counter(
    "codestra_auth_failures_total", "Authentication failures", ["kind"]
)
SCHEMA_REJECTIONS = Counter("codestra_schema_rejections_total", "Schema rejections")
IDEMPOTENT_REPLAYS = Counter("codestra_idempotent_replays_total", "Idempotent replays")
IDEMPOTENCY_CONFLICTS = Counter(
    "codestra_idempotency_conflicts_total", "Idempotency conflicts"
)
QUEUE_DEPTH = Gauge(
    "codestra_delivery_queue_depth", "Delivery queue depth", ["target", "status"]
)
OLDEST_AGE = Gauge(
    "codestra_delivery_oldest_seconds", "Oldest delivery age", ["target"]
)
DLQ_DEPTH = Gauge("codestra_dlq_depth", "Dead-letter queue depth", ["target"])
RECONCILIATION_GAPS = Gauge(
    "codestra_reconciliation_gaps", "Report-only reconciliation gaps", ["category"]
)
SOCIAL_PUBLICATIONS = Gauge(
    "codestra_social_publications", "Social publications by safe state", ["state"]
)
SOCIAL_DEAD_LETTERS = Counter(
    "codestra_social_dead_letters_total", "Social publications dead-lettered"
)
SOCIAL_RECONCILIATION_OLDEST = Gauge(
    "codestra_social_reconciliation_oldest_seconds",
    "Age of the oldest unresolved social reconciliation item",
)
SOCIAL_RETRIES = Counter(
    "codestra_social_retries_total", "Social delivery retries", ["category"]
)
SOCIAL_CALLBACKS = Counter(
    "codestra_social_callbacks_total",
    "Social provider callbacks by privacy-safe outcome",
    ["outcome"],
)

AI_JOBS = Counter(
    "codestra_ai_jobs_total",
    "AI jobs accepted by service and task",
    ["service_code", "task_code"],
)
AI_JOB_STATUS = Counter(
    "codestra_ai_job_status_total",
    "AI job state outcomes",
    ["status"],
)
AI_JOB_DURATION = Histogram(
    "codestra_ai_job_duration_seconds",
    "AI job processing duration",
    ["service_code"],
)
AI_SCHEMA_FAILURES = Counter(
    "codestra_ai_schema_validation_failures_total",
    "AI workflow result schema failures",
)
AI_APPROVALS_PENDING = Gauge(
    "codestra_ai_approvals_pending",
    "AI approvals currently pending",
)
AI_WORKFLOW_RESULTS = Counter(
    "codestra_ai_workflow_results_total",
    "AI workflow results accepted",
    ["status"],
)
AI_RESULT_REPLAYS = Counter(
    "codestra_ai_workflow_result_replays_total",
    "Duplicate AI workflow results acknowledged",
)
AI_OUTBOX_PENDING = Gauge("codestra_ai_outbox_pending", "AI outbox events pending")
AI_RECONCILIATION_PENDING = Gauge(
    "codestra_ai_reconciliation_pending", "AI reconciliation records pending"
)
LEAD_SEARCHES = Counter("codestra_lead_searches_total", "Lead searches created")
LEADS_DISCOVERED = Counter("codestra_leads_discovered_total", "Lead records discovered")
LEADS_DUPLICATES = Counter("codestra_leads_duplicates_total", "Duplicate leads detected")
LEADS_APPROVED = Counter("codestra_leads_approved_total", "Lead reviews approved")
LEAD_IMPORT_REQUESTS = Counter("codestra_lead_import_requests_total", "Lead import requests")
AI_GATEWAY_REQUESTS = Counter(
    "codestra_ai_gateway_requests_total", "AI Gateway requests", ["model_code"]
)
AI_GATEWAY_FAILURES = Counter(
    "codestra_ai_gateway_failures_total", "AI Gateway failures"
)
AI_GATEWAY_DURATION = Histogram(
    "codestra_ai_gateway_request_duration_seconds",
    "AI Gateway request duration",
    ["model_code"],
)
AI_GATEWAY_TIMEOUTS = Counter(
    "codestra_ai_gateway_timeouts_total", "AI Gateway timeouts"
)
AI_GATEWAY_SCHEMA_FAILURES = Counter(
    "codestra_ai_gateway_schema_failures_total", "AI Gateway schema failures"
)
AI_MODEL_HEALTH = Gauge(
    "codestra_ai_model_health", "AI model health state", ["model_code"]
)
AI_MODEL_INPUT_TOKENS = Counter(
    "codestra_ai_model_input_tokens_total", "AI model input tokens", ["model_code"]
)
AI_MODEL_OUTPUT_TOKENS = Counter(
    "codestra_ai_model_output_tokens_total", "AI model output tokens", ["model_code"]
)

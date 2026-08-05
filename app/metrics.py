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
LEAD_REVIEWS = Counter("codestra_lead_reviews_total", "Lead reviews", ["status"])
LEAD_REVIEW_DURATION = Histogram("codestra_lead_review_duration_seconds", "Lead review duration")
LEAD_APPROVALS = Counter("codestra_lead_approvals_total", "Lead approvals", ["decision"])
ODOO_IMPORT_BATCHES = Counter("codestra_odoo_import_batches_total", "Odoo import batches", ["status"])
ODOO_IMPORT_ITEMS = Counter("codestra_odoo_import_items_total", "Odoo import items", ["status"])
ODOO_IMPORT_SUCCESS = Counter("codestra_odoo_import_success_total", "Odoo import successes")
ODOO_IMPORT_FAILURES = Counter("codestra_odoo_import_failures_total", "Odoo import failures")
ODOO_IMPORT_UNKNOWN = Counter("codestra_odoo_import_unknown_total", "Odoo import unknown outcomes")
ODOO_IMPORT_RETRIES = Counter("codestra_odoo_import_retries_total", "Odoo import retries")
ODOO_IMPORT_RECONCILIATION = Counter("codestra_odoo_import_reconciliation_total", "Odoo import reconciliation outcomes", ["status"])
ODOO_IMPORT_DUPLICATES = Counter("codestra_odoo_import_duplicate_blocks_total", "Odoo import duplicate blocks")
ODOO_IMPORT_DURATION = Histogram("codestra_odoo_import_duration_seconds", "Odoo import duration")
VICIDIAL_ELIGIBILITY = Counter("codestra_vicidial_eligibility_checks_total", "VICIdial eligibility checks", ["status"])
VICIDIAL_ASSIGNMENT_BATCHES = Counter("codestra_vicidial_assignment_batches_total", "VICIdial assignment batches", ["status"])
VICIDIAL_ASSIGNMENT_ITEMS = Counter("codestra_vicidial_assignment_items_total", "VICIdial assignment items", ["status"])
VICIDIAL_ASSIGNMENT_SUCCESS = Counter("codestra_vicidial_assignment_success_total", "VICIdial assignment successes")
VICIDIAL_ASSIGNMENT_FAILURES = Counter("codestra_vicidial_assignment_failures_total", "VICIdial assignment failures")
VICIDIAL_ASSIGNMENT_UNKNOWN = Counter("codestra_vicidial_assignment_unknown_total", "VICIdial assignment unknown outcomes")
VICIDIAL_ASSIGNMENT_RETRIES = Counter("codestra_vicidial_assignment_retries_total", "VICIdial assignment retries")
VICIDIAL_ASSIGNMENT_RECONCILIATION = Counter("codestra_vicidial_assignment_reconciliation_total", "VICIdial assignment reconciliation", ["status"])
VICIDIAL_ASSIGNMENT_DUPLICATES = Counter("codestra_vicidial_assignment_duplicate_blocks_total", "VICIdial assignment duplicate blocks")
VICIDIAL_SUPPRESSION_BLOCKS = Counter("codestra_vicidial_assignment_suppression_blocks_total", "VICIdial assignment suppression blocks")
VICIDIAL_LIVE_DIALING_BLOCKS = Counter("codestra_vicidial_live_dialing_blocks_total", "Blocked live dialing attempts")
VICIDIAL_ASSIGNMENT_DURATION = Histogram("codestra_vicidial_assignment_duration_seconds", "VICIdial assignment duration")
VICIDIAL_CAMPAIGN_ACTIVATIONS = Counter("codestra_vicidial_campaign_activations_total", "Campaign activation governance outcomes", ["status"])
VICIDIAL_CANARY_CALLS = Counter("codestra_vicidial_canary_calls_total", "One-call canary outcomes", ["status"])
VICIDIAL_CANARY_BLOCKS = Counter("codestra_vicidial_canary_blocks_total", "Blocked canary actions", ["reason"])
VICIDIAL_CANARY_STOPS = Counter("codestra_vicidial_canary_stops_total", "Emergency and manual canary stops")
VICIDIAL_DIALING_WINDOW_BLOCKS = Counter("codestra_vicidial_dialing_window_blocks_total", "Canary actions outside approved windows")
VICIDIAL_CAPACITY_BLOCKS = Counter("codestra_vicidial_capacity_blocks_total", "Canary capacity gate blocks")
VICIDIAL_CARRIER_CHECKS = Counter("codestra_vicidial_carrier_checks_total", "Canary carrier checks", ["status"])
VICIDIAL_CALL_RESULTS = Counter("codestra_vicidial_call_results_total", "Canary call results", ["status"])
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
AI_CONTROL_CENTER_REQUESTS = Counter("codestra_ai_control_center_requests_total", "Control Center API requests", ["route", "status"])
AI_CONTROL_CENTER_DURATION = Histogram("codestra_ai_control_center_request_duration_seconds", "Control Center API duration", ["route"])
AI_CONTROL_CENTER_ERRORS = Counter("codestra_ai_control_center_errors_total", "Control Center API errors", ["route"])
AI_CONTROL_CENTER_PERMISSION_DENIALS = Counter("codestra_ai_control_center_permission_denials_total", "Control Center permission denials", ["permission"])
AI_CONTROL_CENTER_REALTIME = Gauge("codestra_ai_control_center_realtime_connections", "Control Center realtime connections")
OPS_INCIDENTS = Counter("codestra_operations_incidents_total", "Operations incidents", ["severity", "status"])
OPS_ALERTS = Counter("codestra_operations_alerts_total", "Operations alerts", ["severity", "status"])
OPS_BACKUP_VERIFICATIONS = Counter("codestra_operations_backup_verifications_total", "Backup verification outcomes", ["state"])
OPS_RESTORE_DRILLS = Counter("codestra_operations_restore_drills_total", "Restore drill outcomes", ["status"])
OPS_READINESS_GATES = Gauge("codestra_operations_readiness_gates", "Readiness gates by status", ["status"])

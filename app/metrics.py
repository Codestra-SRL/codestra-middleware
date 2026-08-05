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

ORDER_RECEIVED = Counter("codestra_orders_received_total", "Orders received")
ORDER_VALIDATED = Counter("codestra_orders_validated_total", "Orders validated")
ORDER_APPROVED = Counter("codestra_orders_approved_total", "Orders approved")
ORDER_DISPATCHED = Counter("codestra_orders_dispatched_total", "Orders dispatched")
ORDER_STARTED = Counter("codestra_orders_started_total", "Orders started")
ORDER_COMPLETED = Counter("codestra_orders_completed_total", "Orders completed")
ORDER_FAILED = Counter("codestra_orders_failed_total", "Orders failed")
ORDER_RETRIED = Counter("codestra_orders_retried_total", "Orders retried")
ORDER_DEAD_LETTERED = Counter("codestra_orders_dead_lettered_total", "Orders dead-lettered")
ORDER_HUMAN_REVIEW = Counter("codestra_orders_human_review_total", "Orders sent to human review")
ORDER_DUPLICATE_SUPPRESSION = Counter("codestra_order_duplicate_suppression_total", "Duplicate orders suppressed")
ORDER_CALLBACK_FAILURE = Counter("codestra_order_callback_failure_total", "Order callback failures")
ORDER_PROGRESS = Counter("codestra_order_progress_total", "Order progress callbacks")
ORDER_SECURITY_RETRY = Counter("codestra_security_failure_retry_total", "Security failures never retried")
ORDER_RECONCILIATION_MISMATCH = Counter("codestra_order_reconciliation_mismatch_total", "Order reconciliation mismatches")
ORDER_QUEUE_DEPTH = Gauge("codestra_order_queue_depth", "Approved-order queue depth")
ORDER_STALE_RUNNING = Gauge("codestra_order_stale_running_total", "Stale running orders")
ORDER_WORKFLOW_DURATION = Histogram("codestra_order_workflow_duration_seconds", "Order workflow duration")
ORDER_QUEUE_DELAY = Histogram("codestra_order_queue_delay_seconds", "Order queue delay")

# Provider metrics deliberately use stable operation/status labels only.
AI_TASKS_RECEIVED = Counter("codestra_ai_tasks_received_total", "AI tasks received", ["task_type", "status"])
AI_TASK_FAILURES = Counter("codestra_ai_task_failures_total", "AI task failures", ["task_type", "failure_class"])
AI_TASK_DURATION = Histogram("codestra_ai_task_duration_seconds", "AI task duration", ["task_type"])
VICIDIAL_COMMANDS_RECEIVED = Counter("codestra_vicidial_commands_received_total", "VICIdial commands received", ["command_type", "status"])
VICIDIAL_COMMAND_FAILURES = Counter("codestra_vicidial_command_failures_total", "VICIdial command failures", ["command_type", "failure_class"])
VICIDIAL_COMMAND_DURATION = Histogram("codestra_vicidial_command_duration_seconds", "VICIdial command duration", ["command_type"])
POSTIZ_COMMANDS_RECEIVED = Counter("codestra_postiz_commands_received_total", "Postiz commands received", ["command_type", "status"])
POSTIZ_COMMAND_FAILURES = Counter("codestra_postiz_command_failures_total", "Postiz command failures", ["command_type", "failure_class"])
POSTIZ_COMMAND_DURATION = Histogram("codestra_postiz_command_duration_seconds", "Postiz command duration", ["command_type"])
CROSS_SYSTEM_QUEUE_DEPTH = Gauge("codestra_cross_system_queue_depth", "Cross-system queue depth")
CROSS_SYSTEM_CALLBACK_FAILURES = Counter("codestra_cross_system_callback_failures_total", "Cross-system callback failures", ["provider"])
CROSS_SYSTEM_DEAD_LETTER = Counter("codestra_cross_system_dead_letter_total", "Cross-system dead letters", ["provider"])
CROSS_SYSTEM_RECONCILIATION_MISMATCH = Counter("codestra_cross_system_reconciliation_mismatch_total", "Cross-system reconciliation mismatches", ["provider"])
CROSS_SYSTEM_STALE_EXECUTION = Gauge("codestra_cross_system_stale_execution_total", "Stale cross-system executions")

# Logistics labels are intentionally low-cardinality and contain no customer data.
LOGISTICS_ORDERS = Counter("codestra_logistics_orders_total", "Logistics orders")
LOGISTICS_SHIPMENTS = Counter("codestra_logistics_shipments_total", "Logistics shipments")
LOGISTICS_SHIPMENTS_BY_STATUS = Gauge("codestra_logistics_shipments_by_status", "Shipments by status", ["status"])
LOGISTICS_ACTIVE_LOADS = Gauge("codestra_logistics_active_loads", "Active logistics loads")
LOGISTICS_DISPATCH_FAILURES = Counter("codestra_logistics_dispatch_failures_total", "Dispatch failures", ["reason"])
LOGISTICS_STATUS_EVENTS = Counter("codestra_logistics_status_events_total", "Shipment status events", ["status"])
LOGISTICS_EXCEPTIONS = Counter("codestra_logistics_exceptions_total", "Logistics exceptions", ["type"])
LOGISTICS_CLAIMS = Counter("codestra_logistics_claims_total", "Logistics claims", ["status"])
LOGISTICS_PROOF_EVENTS = Counter("codestra_logistics_proof_events_total", "Proof events", ["type"])
LOGISTICS_TRACKING_REQUESTS = Counter("codestra_logistics_tracking_requests_total", "Tracking requests", ["result"])
LOGISTICS_TRACKING_DENIALS = Counter("codestra_logistics_tracking_denials_total", "Tracking denials", ["reason"])
LOGISTICS_NOTIFICATIONS = Counter("codestra_logistics_notifications_total", "Logistics notifications", ["channel", "status"])
LOGISTICS_INVOICE_REQUESTS = Counter("codestra_logistics_invoice_requests_total", "Invoice requests", ["status"])
LOGISTICS_RECONCILIATION_PENDING = Gauge("codestra_logistics_reconciliation_pending", "Pending reconciliation", ["system"])

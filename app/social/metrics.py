from prometheus_client import Counter, Gauge, Histogram

publish_requests = Counter(
    "social_publish_requests_total",
    "Social publish requests",
    ("provider", "network", "result"),
)
publish_success = Counter(
    "social_publish_success_total",
    "Successful social publishes",
    ("provider", "network"),
)
publish_failures = Counter(
    "social_publish_failures_total",
    "Failed social publishes",
    ("provider", "network", "result"),
)
publish_duration = Histogram(
    "social_publish_duration_seconds", "Social publish latency", ("provider", "network")
)
provider_requests = Counter(
    "social_provider_requests_total", "Provider requests", ("provider", "result")
)
provider_errors = Counter(
    "social_provider_errors_total", "Provider errors", ("provider", "result")
)
provider_rate_limits = Counter(
    "social_provider_rate_limits_total", "Provider rate limits", ("provider",)
)
webhooks_received = Counter(
    "social_webhooks_received_total", "Social webhooks received", ("provider", "result")
)
webhooks_rejected = Counter(
    "social_webhooks_rejected_total", "Social webhooks rejected", ("provider", "result")
)
queue_depth = Gauge("social_queue_depth", "Social queue depth", ("provider",))
jobs_retried = Counter(
    "social_jobs_retried_total", "Social jobs retried", ("provider", "result")
)
jobs_deadletter = Counter(
    "social_jobs_deadletter_total", "Social jobs dead-lettered", ("provider", "result")
)

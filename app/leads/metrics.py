from prometheus_client import Counter, Gauge, Histogram

identity_resolution = Counter(
    "identity_resolution_total", "Identity resolutions", ("result", "confidence")
)
identity_conflicts = Counter(
    "identity_conflicts_total", "Identity conflicts", ("type",)
)
lead_created = Counter("lead_created_total", "Canonical leads created", ("source",))
lead_deduped = Counter("lead_deduped_total", "Lead events deduplicated", ("source",))
lead_scores = Histogram(
    "lead_score_distribution", "Lead scores", buckets=(0, 20, 40, 60, 80, 100)
)
next_actions = Counter("next_best_action_total", "Next actions", ("action", "eligible"))
dnc_blocks = Counter("dnc_blocks_total", "DNC blocks", ("channel",))
consent_blocks = Counter("consent_blocks_total", "Consent blocks", ("channel",))
attribution_calculations = Counter(
    "attribution_calculations_total", "Attribution calculations", ("model",)
)
revenue_events = Counter("revenue_events_total", "Revenue events", ("type", "currency"))
attributed_revenue = Counter(
    "attributed_revenue_amount",
    "Attributed revenue in original currency units",
    ("currency", "model"),
)
attribution_recalculations = Counter(
    "attribution_recalculation_total", "Attribution recalculations", ("model",)
)
identity_review_queue = Gauge(
    "identity_review_queue", "Unresolved identity review candidates"
)

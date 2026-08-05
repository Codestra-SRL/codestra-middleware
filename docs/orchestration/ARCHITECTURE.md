# Orchestration architecture

PostgreSQL owns commands, workflows, results, retries, and audit. Redis carries only
temporary queues, locks, rate limits, presence, and coordination. n8n executes approved
workflow versions but never owns authorization or business state.

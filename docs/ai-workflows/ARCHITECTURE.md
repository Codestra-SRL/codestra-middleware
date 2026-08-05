# AI Workflow Architecture

PostgreSQL on `65.109.65.169` is authoritative for goals, plans, versions, instances, tasks, waits, approvals, leases, events, costs, and audit. Qwen proposes structured plans only. Every external action goes through the middleware tool gateway and a durable checkpoint.

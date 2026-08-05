# Controlled Odoo-to-VICIdial assignment

Middleware owns eligibility, human approval, assignment batches, stable external keys, retries, and reconciliation. The adapter is the only VICIdial write path. n8n is orchestration only; Qwen recommendations are advisory.

Default target identifiers are `STAGING_CAMPAIGN` and `STAGING_LEADS`; production campaigns and dialing are rejected by policy and flags.

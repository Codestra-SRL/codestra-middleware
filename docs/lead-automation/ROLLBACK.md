# Lead Automation V1 rollback

Disable all lead-automation kill switches and the `n8n.leads.ingest` binding first. Preserve events, payload hashes, outbox rows, attempts, results, acknowledgements, quarantine, reconciliation, and audit evidence. Stop only the lead dispatcher and reconciliation worker. Downgrade migration `0028_lead_automation_v1` only after confirming zero business rows and taking an owner-approved backup. Do not modify recording, telephony, Asterisk, or VICIdial resources.

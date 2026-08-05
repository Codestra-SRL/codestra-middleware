# Controlled production expansion

Expansion is fail-closed and sequential. Server A (65.109.65.169) owns approvals, limits, observation windows, audit, rollback and reconciliation. Server B (5.9.108.250) provides private AI inference; Server C (49.12.145.107) is restricted to allowlisted scraper tests; Server D (65.21.67.207) is restricted to disabled-list VICIdial staging.

No stage may run without signed expansion approval, a maintenance window, verified backups and rollback authority. Runtime execution is currently blocked because server access and those approvals are unavailable.

Stages: AI internal workload, scraper, contact verification, Odoo import, VICIdial disabled-list assignment, Call Intelligence and Agent Assist. Live dialing, campaign activation, bulk scraping, automatic approval and customer-facing actions remain disabled.

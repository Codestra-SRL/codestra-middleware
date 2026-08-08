# n8n staging runbook

1. Verify exact middleware SHA/image digest and migration head.
2. Confirm every production/write/outreach flag remains false.
3. Confirm staging n8n is 2.30.8 in queue mode with two workers at concurrency
   five, PostgreSQL persistence, and authenticated private Redis 7.4.5.
4. Register only `TEST_SYN_*` workflows with explicit tenant scope and disabled
   state first. Review before enabling the synthetic mapping.
5. Apply migration, deploy the exact image to staging only, and verify health.
6. Run dispatch, signed callback, ten-request duplicate, replay, restart, and
   concurrency tests at 1/5/10/25.
7. Confirm one logical execution/result and zero Odoo/VICIdial/outreach writes.
8. Observe n8n/Redis metrics and retain the PostgreSQL/audit identifiers.

Workflow inventory at discovery: 236 total, 0 active, 236 inactive. Without a
signed governance inventory, inactive workflows remain `UNKNOWN` except
explicitly approved synthetic fixtures; nothing is deleted or activated.

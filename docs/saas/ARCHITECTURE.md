# SaaS architecture

Server A (65.109.65.169) owns tenant identity, plans, entitlements, provisioning, billing state, usage, suspension and audit. Server B (5.9.108.250) reports tenant-scoped AI usage only. Server C (49.12.145.107) is limited to signup/domain routing and health. Server D (65.21.67.207) remains a read-only tenant-safe telephony adapter.

Production signup, real billing, automatic suspension and deletion are disabled in this foundation.

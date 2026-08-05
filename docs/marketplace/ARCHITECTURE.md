# Marketplace architecture

Server A (65.109.65.169) owns catalog, publisher approval, manifests, tenant installations, entitlements, lifecycle, audit and rollback. Server B (5.9.108.250) handles private AI prompt/schema/model-policy packages. Server C (49.12.145.107) provides connector workers and health only. Server D (65.21.67.207) exposes allowlisted read-only telephony adapter operations.

Production installation, community publishing, real marketplace billing and destructive uninstall are disabled.

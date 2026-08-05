# One-call authorization

Written authorization, approver identity, approved test number, rollback
authority, maintenance window, and carrier/test endpoint are required before a
live call. The middleware stores only a SHA-256 hash of the allowlisted number.
No authorization is present in the current environment, so the live path is
fail-closed.

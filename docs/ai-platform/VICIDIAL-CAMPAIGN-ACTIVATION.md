# VICIdial campaign activation governance

Activation is a separately approved, staging-only operation. It requires a
written authorization reference, an explicit maintenance window, an approved
staging campaign/list, carrier and agent-capacity checks, and a zero-hopper
snapshot. Production activation and live dialing remain disabled by default.

The middleware records approval and shutdown state; n8n cannot select arbitrary
campaigns or bypass these gates. Runtime activation is blocked unless the
dedicated canary flags and authorization are explicitly enabled.

# Tool Gateway architecture

Middleware on 65.109.65.169 is the sole authorization and execution control plane. AI services return structured requests only; adapters are scoped, audited, idempotent, and never expose credentials.

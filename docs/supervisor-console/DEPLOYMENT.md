# Staging deployment

Deploy only after exact-head CI and review. Keep `SUPERVISOR_PRODUCTION_ENABLED=false`, agent/campaign commands off, recording access off and all existing write kill switches off. Apply migration 0030 forward, validate health/auth/scope/SSE, then expose only `staging-supervisor.codestra.co` through the existing authenticated proxy. Production deployment is prohibited.

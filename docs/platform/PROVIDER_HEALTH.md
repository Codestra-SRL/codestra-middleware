# Provider health

Provider health stores API reachability, authentication, latency, error rate and polling lag as separate components plus a 0–100 summary. States are HEALTHY, DEGRADED, UNAVAILABLE, AUTH_REQUIRED and NOT_CONFIGURED.

`GET /api/v1/social/providers/health` exposes configuration booleans and safe components. It never probes a disabled provider or reveals credentials. Health cannot trigger automatic failover.

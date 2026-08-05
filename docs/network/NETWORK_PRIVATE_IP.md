# Private Address Registry

| Address | Owner | Status | Allowed purpose |
|---|---|---|---|
| 10.40.0.1/24 | Middleware | verified | private ingress/control plane |
| 10.40.0.2/24 | VICIdial | registered, unreachable | callbacks and restricted provisioning |
| 10.40.0.4/24 | Qwen | verified reachable | outbound mTLS/HMAC worker/authentication |
| unassigned | Web zone | public-only | approved HTTPS APIs through middleware |

Private DNS does not publish `middleware.internal.codestra.agency`; clients use
the private IP with explicit SNI and the approved private CA. No private
gateway or private DNS default route is configured on middleware.

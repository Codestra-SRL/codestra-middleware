# Provider parity

| Capability | Postly | Hootsuite | Codestra behavior |
|---|---|---|---|
| Account discovery | Adapter support | `GET /v1/socialProfiles` | Normalized accounts |
| Create/schedule | Adapter support | `POST /v1/messages` | Provider-neutral post/job |
| Cancel/delete | Adapter support | `DELETE /v1/messages/{id}` | Normalized state |
| Update | Runtime-dependent | Not documented | Capability error |
| Image/multi-image/video | Adapter support | Media upload plus message media | Normalized media reference |
| Analytics | Runtime-dependent | Separate API not certified | Capability error |
| Events | Signed Middleware contract | Polling | Normalized events |
| Idempotency | Middleware | Middleware | Durable Codestra idempotency |
| Reconciliation | Provider lookup | `GET /v1/messages/{id}` | Fail closed after unknown send |

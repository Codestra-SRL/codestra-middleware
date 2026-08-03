# Postly deployment inventory

Evidence captured 2026-08-02 UTC. This inventory contains no secret values.

| Item | Verified value |
|---|---|
| Host | `49.12.145.107`, local interface `enp5s0` |
| Public URL | `https://social.codestra.co` (HTTPS 200, Caddy TLS termination) |
| Compose | `/srv/postiz/compose.production.yaml`, project `postiz` |
| Upstream | `gitroomhq/postiz-app`, release `v2.22.1`, commit `c90b6c625bc0ec470d6dcdb57c63608aaa9b7b74` |
| Image | `ghcr.io/gitroomhq/postiz-app:v2.22.1`, digest `sha256:edcc9a8e3bfaafac72ccae30b630e5eed873b9538f726fcb97c5a7529e6ed10a` |
| Services | Postiz, PostgreSQL 17, Redis 7.2, Temporal 1.28.1, Temporal tools/UI/PostgreSQL 16, Elasticsearch 7.17.27; all healthy |
| Exposure | No host-published ports for Postiz database, Redis, Temporal, Elasticsearch, workers, or media storage |
| Caddy | Existing route proxies `social.codestra.co` to `postiz:5000`; unrelated routes preserved |
| Baseline | `users=1`, `organizations=1`, `integrations=0`, `posts=0`, `media=0`, `webhooks=0` |
| Backup | encrypted Restic repository outside volumes; snapshot `8b16ff1e`; `LAST_SUCCESS=2026-08-02T19:02:25Z`; timer enabled |
| Restore | logical dump catalog validation and isolated PostgreSQL restore passed (69 tables and expected counts) |
| Rollback | `/srv/postiz/documentation/rollback.md` |
| Branding | versioned candidate exists but production remains pinned upstream; authoritative logo/public source publication remain blockers |

Files that a future private-API activation could change are the Compose overlay, Caddy configuration, monitoring rules, and a dedicated secret reference. No production configuration was changed for this contract-only phase.

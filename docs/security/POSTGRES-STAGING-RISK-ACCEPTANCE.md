# PostgreSQL isolated-staging security-risk acceptance package

Status: **unapproved — security-owner decision required**

The official PostgreSQL 17.10 Alpine image remains pinned at
`postgres@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193`.
The findings are in the Go standard library embedded in
`/usr/local/bin/gosu`; they are not PostgreSQL server packages. No official
PostgreSQL 17 digest tested on July 31, 2026 cleared them. Custom images and
in-place binary replacement are prohibited by this mission.

Trivy reported 1 CRITICAL and 14 HIGH records. Grype reported additional CVE
records and Go advisory aliases. Scanner disagreement is preserved and is not
a pass.

## Remaining CVEs

All records affect `stdlib` compiled with Go 1.24.6 in `gosu`. Every listed
record has a newer Go toolchain version reported by at least one scanner, but
no official PostgreSQL 17 image containing the rebuilt binary was available.

| CVE | Severity observed | Fixed Go version reported |
|---|---|---|
| CVE-2025-58187 | HIGH | 1.24.9 / 1.25.3 |
| CVE-2025-58188 | HIGH | 1.24.8 / 1.25.2 |
| CVE-2025-61723 | HIGH | 1.24.8 / 1.25.2 |
| CVE-2025-61725 | HIGH | 1.24.8 / 1.25.2 |
| CVE-2025-61726 | HIGH | 1.24.12 / 1.25.6 |
| CVE-2025-61729 | HIGH | 1.24.11 / 1.25.5 |
| CVE-2025-61731 | HIGH | 1.24.12 / 1.25.6 |
| CVE-2025-61732 | HIGH | 1.24.13 / 1.25.7 |
| CVE-2025-68121 | CRITICAL | 1.24.13 / 1.25.7 |
| CVE-2026-25679 | HIGH | 1.25.8 / 1.26.1 |
| CVE-2026-27140 | HIGH | 1.25.9 / 1.26.2 |
| CVE-2026-27143 | CRITICAL (Grype) | 1.25.9 / 1.26.2 |
| CVE-2026-27144 | HIGH | 1.25.9 / 1.26.2 |
| CVE-2026-27145 | HIGH | 1.25.11 / 1.26.4 |
| CVE-2026-32280 | HIGH | 1.25.9 / 1.26.2 |
| CVE-2026-32281 | HIGH | 1.25.9 / 1.26.2 |
| CVE-2026-32283 | HIGH | 1.25.9 / 1.26.2 |
| CVE-2026-33811 | HIGH | 1.25.10 / 1.26.3 |
| CVE-2026-33814 | HIGH | 1.25.10 / 1.26.3 |
| CVE-2026-39820 | HIGH | 1.25.10 / 1.26.3 |
| CVE-2026-39822 | HIGH | 1.25.12 / 1.26.5 |
| CVE-2026-39836 | HIGH | 1.25.10 / 1.26.3 |
| CVE-2026-42499 | HIGH | 1.25.10 / 1.26.3 |
| CVE-2026-42501 | HIGH | 1.25.10 / 1.26.3 |
| CVE-2026-42504 | HIGH | 1.25.11 / 1.26.4 |

## Isolated-staging exploitability and controls

`gosu` is used only by the official entrypoint to drop from the container's
initial user to the `postgres` account. The database has no public port, lives
on an internal Docker network, accepts only staging credentials, contains only
synthetic data, and has no production route. The container drops unnecessary
capabilities and applies process, CPU, memory, and log limits.

These controls reduce exposure but do not remove the vulnerable compiled code.
Acceptance, if granted, must be isolated-staging-only, expire no later than
August 30, 2026, and be revoked immediately when a fixed official PostgreSQL 17
digest appears or any isolation control fails.

Production deployment and activation remain blocked.

# Middleware campaign/outbox branch recovery

Date: 2026-07-27

## Preserved checkout

The original authoritative middleware checkout remains at
`/opt/codestra/middleware`, commit `cbc9e54c7f5a`, branch
`security/rc3p-signing-ancestry-fix`. Its upstream branch was deleted and its
modified `deploy/compose.runtime.yaml` was not changed.

Protected preservation directory:

`/root/codestra-middleware-compose-preservation-20260727T223000Z`

It contains the original file, SHA-256 checksum, binary diff, complete Git
status, and original commit. The Compose SHA-256 is
`810154d3f0cb33d7f3510affc19f2754a315d6312a63c9cc7d809d4d2a0c5b2c`.

## Lineage decision

The platform repository at `/root/codestra-production-completion` owns
`release/production-activation` and the initial `campaign_provisioning`
checkpoint. The middleware is a separate related-history repository at
`https://github.com/Codestra-SRL/codestra-middleware.git`; it has no
`release/production-activation` ref.

The clean implementation worktree was therefore created from the middleware's
current `origin/main` at `b4fd4dd7e46d` and named
`feature/middleware-campaign-outbox`. This preserves authoritative middleware
lineage rather than copying a repository snapshot.

Other inspected middleware worktrees are historical feature, remediation,
release-candidate, or build worktrees in the same Git history. None supersedes
current `origin/main`. The platform VICIdial worktree is related to the
platform release branch but is not the middleware history.

The Odoo addon checkout at `/opt/codestra/odoo-addons` is a separate local Git
history with existing unrelated changes and no configured remote. It was
inspected read-only and not modified.

## Implementation boundary

This branch contains source-only campaign preview, persistent immutable
revisions, event receipts, atomic list reservations, retry/dead-letter state,
approval separation, audit correlation fields, and disabled production
defaults.

It does not include the preserved Compose draft, runtime environments, secrets,
databases, generated credentials, caches, backups, or deployment changes.
No container, database, workflow, firewall, telephony service, or feature flag
was changed.

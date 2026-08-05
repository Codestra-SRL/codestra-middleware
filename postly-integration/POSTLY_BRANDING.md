# Codestra Postly branding boundary

The customer-facing name for the upstream Postiz installation is **Codestra
Postly**. Branding is implemented as a presentation-layer change only: the
upstream package names, source notices, copyright statements, and license
files remain intact so upgrades and attribution remain safe.

## Required staging changes

When the Postiz source or deployment host is available, apply the approved
Codestra logo and product strings to the login, navigation, metadata, email,
empty-state, error, invitation, and share-page presentation surfaces. Keep the
upstream product identifier in diagnostics and package metadata. Do not put
credentials or provider tokens in branding configuration.

## Current verified boundary

The middleware repository contains the mock-only Postly control plane and
sanitized adapter contracts. The deployed Postiz source is external to this
repository (`gitroomhq/postiz-app` v2.22.1, recorded in
`POSTLY_DEPLOYMENT_INVENTORY.md`), so production UI branding has not been
claimed or changed from this checkout. Applying it requires an owner-approved
staging checkout of that source and the authoritative Codestra logo asset.

Live publishing remains disabled while that external deployment work is
pending.

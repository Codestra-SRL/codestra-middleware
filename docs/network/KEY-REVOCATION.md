# Mesh-key revocation

Locate keys by their unique comment and confirm the fingerprint before editing.
Remove exactly the matching complete line from every destination's
`authorized_keys`, preserving root ownership and mode 0600. Reloading SSH is not
required for `authorized_keys` changes.

Verify revocation using the retired identity with batch mode, strict host
checking, and `IdentitiesOnly=yes`. Authentication must fail. Verify a separate
emergency/operator path before closing the console.

Server A's synthetic revocation rehearsal passed on 2026-08-05: the synthetic
key authenticated over loopback, its authorization was removed, and the same
key was rejected. The synthetic key material was then destroyed. No production
or Codex key was revoked.

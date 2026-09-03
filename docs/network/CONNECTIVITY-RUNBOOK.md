# Connectivity runbook

## Per-server local session

1. Record host identity, OS, addresses, routes, VLAN, MTU, neighbors, SSH
   effective settings, firewall, listeners, and critical service health.
2. On D, record active calls before any change. Do not restart networking while
   calls are active.
3. Back up SSH, firewall, authorized keys, and persistent network configuration
   into a root-only timestamped directory.
4. Generate only that server's `codestra_mesh_from_<zone>_ed25519` identity.
5. Return its comment and fingerprint; transfer only the `.pub` file through an
   authenticated operator channel.
6. Verify destination host fingerprints locally at the destination console.
7. Install only documented trust paths with source and forwarding restrictions.
8. Validate `sshd -t`, reload SSH, and confirm the listener.
9. Test route, neighbor, ICMP as supporting evidence, TCP/22, strict SSH, then
   the approved TLS application contract.
10. Recheck service health and default routes.

## Server A completed work

- Created the dedicated A identity without exposing its private key.
- Enforced public-key authentication, disabled password/keyboard-interactive
  authentication, and set root login to key-only.
- Validated and reloaded SSH successfully.
- Did not narrow the emergency public SSH firewall rule because remote mesh
  authentication is not yet established.
- Authorized B's dedicated B-to-A public identity from `10.40.0.4` only on
  2026-08-06 after exact fingerprint verification. The destination-side
  configuration validates; B must still prove authentication from its local
  session.

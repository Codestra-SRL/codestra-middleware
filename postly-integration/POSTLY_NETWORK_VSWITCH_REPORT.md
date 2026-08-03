# Network and vSwitch verification

Read-only inspection on 2026-08-02 found no `10.40.0.x` address, no interface secondary address, no route for `10.40.0.0/16` (or narrower route), and no matching netplan/system configuration on the Postly host. The Middleware private address therefore cannot be verified and private ICMP/TCP tests cannot be safely targeted.

Public DNS for `api.codestra.agency`, `n8n.codestra.agency`, and `n8n-staging.codestra.agency` resolves to `65.109.65.169`; HTTPS and certificates respond. Public HTTPS is evidence of TLS termination on that service host, not evidence of vSwitch connectivity. `social.codestra.co` terminates TLS at local Caddy.

Required network change (separate authorized maintenance): obtain both Hetzner vSwitch IP assignments and prefix, configure persistent routes, restrict the adapter listener to the private interface and Middleware source, then test ICMP only if allowed and TCP/TLS on the selected adapter port. No insecure public fallback was configured.

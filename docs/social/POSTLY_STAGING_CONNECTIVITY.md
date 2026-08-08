# Postly staging connectivity

Observed Middleware Server A topology:

- public: `65.109.65.169/32` on `enp41s0`;
- private: `10.40.0.1/24` on VLAN interface `enp41s0.4001`;
- VLAN ID: `4001`;
- VLAN MTU: `1400`;
- expected Postly peer: `10.40.0.2`;
- public default route: `65.109.65.129` on `enp41s0`, unchanged.

The private peer did not answer ARP/ICMP/TCP during Phase 2 discovery. Public SSH to `49.12.145.107` rejected the dedicated local identity. No firewall, route, VLAN, proxy, or public exposure change was made.

When access is restored, validate symmetric routes, neighbor discovery, MTU, private TLS identity, and a narrowly allowed Postly API port before setting `POSTIZ_INTERNAL_BASE_URL` to the private endpoint.

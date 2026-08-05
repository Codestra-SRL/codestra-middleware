# vSwitch VLAN 4001

## Required topology

- Network: `10.40.0.0/24`
- VLAN: `4001`
- MTU: `1400`
- Private gateway: none
- Public default routes: unchanged

## Observed from Server A

- Manager: Netplan rendered to `systemd-networkd`.
- Persistent definition: `/etc/netplan/60-vswitch.yaml`.
- A `10.40.0.1`: configured and operational.
- B `10.40.0.4`: route via `enp41s0.4001`, neighbor resolved, ICMP and TCP/22 pass.
- D `10.40.0.2`: route exists but neighbor remains incomplete; ICMP, TCP/22, and TCP/443 fail.
- C: no private address may be inferred.

Do not restart networking globally. D requires a destination-local inventory of
VLAN interface, tag, MTU, address, route, and active calls before a guarded
repair. C requires authoritative vSwitch membership and an unused allocation.

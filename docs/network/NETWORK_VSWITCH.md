# vSwitch and VLAN 4001

Middleware interface `enp41s0.4001@enp41s0` is UP/LOWER_UP, uses 802.1Q VLAN
ID 4001, address 10.40.0.1/24, and MTU 1400. It has no private default gateway;
the public default route remains on `enp41s0` via 65.109.65.129.

Neighbor evidence:

| Address | MAC learned | State |
|---|---|---|
| 10.40.0.4 | bc:fc:e7:69:04:d1 | STALE/reachable on probe |
| 10.40.0.2 | none; neighbor state `INCOMPLETE` | unreachable at Layer 2 |

The comparison probe learned Qwen's MAC immediately while VICIdial remained
`INCOMPLETE`. Middleware selected the same directly connected VLAN interface
and source address for both destinations, and the VLAN interface reported zero
RX/TX errors or drops. This isolates the current failure to the VICIdial/vSwitch
side of the Layer-2 path rather than middleware routing or VLAN health.

No Netplan, VLAN, route, MTU, or firewall state was changed. Remediation for
10.40.0.2 must occur in the VICIdial local zone: verify its tagged VLAN 4001
interface, address, MTU, switch attachment, and source firewall before any
middleware-side change is considered.

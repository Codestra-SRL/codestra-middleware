# Network Health

| Control | Result |
|---|---|
| Middleware identity | pass |
| Public default route unchanged | pass |
| VLAN 4001 link and MTU | pass |
| Qwen private reachability | pass |
| VICIdial private reachability | fail; ARP/neighbor resolution incomplete |
| Web public HTTPS | pass |
| Middleware DNS/TLS services | pass |
| NTP synchronization | pass |
| UFW default deny | pass |
| Internal databases publicly exposed | none observed |
| Docker verifier isolation | pass |
| Remote reverse-direction matrix | blocked by zone-local execution |
| Bandwidth matrix | not measured; no approved endpoint |

Overall status is degraded/partial: the control plane and Qwen path are
healthy, but the required VICIdial private path is not reachable.

The failure is localized: both 10.40.0.2 and 10.40.0.4 route directly through
`enp41s0.4001` using source 10.40.0.1, but only Qwen resolves a MAC address.
Middleware VLAN counters contain no errors or drops.

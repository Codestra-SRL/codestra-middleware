# Network Health

| Control | Result |
|---|---|
| Middleware identity | pass |
| Public default route unchanged | pass |
| VLAN 4001 link and MTU | pass |
| Qwen private reachability | pass |
| VICIdial private reachability | fail |
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

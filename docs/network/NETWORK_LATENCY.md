# Network Latency and Loss

Three ICMP samples were collected from middleware. These are reachability
samples, not capacity benchmarks.

| Destination | Path | Loss | RTT min/avg/max ms | Status |
|---|---|---:|---:|---|
| Qwen 10.40.0.4 | VLAN 4001 | 0% | 26.328/26.425/26.567 | pass |
| Qwen 5.9.108.250 | public | 0% | 26.469/26.501/26.551 | pass |
| Web 49.12.145.107 | public | 0% | 25.186/25.948/26.359 | pass |
| VICIdial 10.40.0.2 | VLAN 4001 | 100% | unavailable | fail |
| VICIdial 65.21.67.207 | public | 100% | ICMP filtered/unavailable | inconclusive |

TCP reachability proves Qwen SSH and Web SSH/HTTP/HTTPS. It does not prove
application authorization. Bidirectional latency, jitter, bandwidth, and
packet-loss matrices require the remote runbook on all three zones. No flood or
destructive load test is authorized.

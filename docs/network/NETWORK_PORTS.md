# Port Matrix

## Middleware public listeners

| Port | Service | Exposure |
|---:|---|---|
| 22/tcp | OpenSSH | public administration |
| 80/tcp | Caddy | public HTTP redirect/ACME |
| 443/tcp | Caddy | public and SNI-routed private TLS |

Loopback-only listeners include DNS 53, NATS 4222/8222, preview ports
19069/31880/31881, and a disposable PostgreSQL mapping. Application and data
containers expose ports only inside Docker bridges.

## Middleware-origin probes

Exit code zero means the TCP handshake completed.

| Target | 22 | 80 | 443 | 8443 | 8444 |
|---|---:|---:|---:|---:|---:|
| 10.40.0.2 | closed/unreachable | closed | closed | closed | closed |
| 10.40.0.4 | open | closed | closed | closed | closed |
| 65.21.67.207 | filtered/unreachable | filtered | filtered | filtered | filtered |
| 5.9.108.250 | open | closed | closed | closed | closed |
| 49.12.145.107 | open | open | open | closed | closed |

This is a bounded required-port probe, not a general port scan.

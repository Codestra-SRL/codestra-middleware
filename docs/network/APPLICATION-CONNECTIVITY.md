# Application connectivity

Recorded 2026-08-05 from Server A:

| Source | Destination | Port | Result | Notes |
|---|---|---:|---|---|
| A | B private 10.40.0.4 | 22 | Pass | About 30 ms TCP; administration only |
| A | B private 10.40.0.4 | 443 | Blocked | No approved private HTTPS listener observed |
| A | C public 49.12.145.107 | 443 | Pass | TLS 1.3, certificate `social.codestra.co`, verification passed |
| A | D private 10.40.0.2 | 22/443 | Blocked | Neighbor resolution failed |
| B | A private 10.40.0.1 | 443 | Pending | Must be tested from B with the existing application mTLS/HMAC identity |
| D | A private 10.40.0.1 | approved API | Pending | Must be tested locally from D without executing a command |
| C | A canonical HTTPS | 443 | Pending | Must be tested locally from C |

TCP reachability is not an application acceptance test. Every application path
also requires the approved TLS server name, certificate validation,
authentication, method, safe synthetic request, response status, and latency.

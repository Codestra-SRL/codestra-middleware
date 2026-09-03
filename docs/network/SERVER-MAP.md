# Codestra server map

| Zone | Public address | Private address | Role | Evidence status |
|---|---|---|---|---|
| A | 65.109.65.169 | 10.40.0.1/24 | Middleware, Odoo, n8n, PostgreSQL, Redis, control | Locally verified 2026-08-05 |
| B | 5.9.108.250 | 10.40.0.4/24 | Qwen, Whisper, TTS, Qdrant | Private ARP, ICMP, and SSH TCP reachable from A; local inventory pending B session |
| C | 49.12.145.107 | Unknown | Website, Postiz, scraper, marketplace | Public SSH and HTTPS reachable; VLAN membership/address unverified |
| D | 65.21.67.207 | 10.40.0.2/24 expected | VICIdial, Asterisk, telephony | No tagged neighbor resolution from A; local inventory and active-call check pending D session |

Server A uses `enp41s0.4001`, VLAN 4001, MTU 1400, and has no private
gateway. Its public default route remains through `enp41s0`.

Each server is an independent administration zone. Cross-host SSH is a
revocable operational facility, not an application identity and not a
requirement for normal application traffic.

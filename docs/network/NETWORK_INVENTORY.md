# Codestra Network Inventory

Evidence captured from the middleware control plane on 2026-08-05 UTC. Remote
administrative SSH is intentionally absent; remote OS-level fields are marked
unverified rather than inferred from historical files.

| Zone | Role | Hostname | OS/kernel | Public | Private | IPv6 | Current health |
|---|---|---|---|---|---|---|---|
| A | Middleware/Odoo/n8n | `middleware` | Ubuntu 22.04; 5.15.0-186 | 65.109.65.169 | 10.40.0.1/24 | 2a01:4f9:5a:558e::2/64 | local services healthy |
| B | VICIdial/Asterisk | remote-unverified | remote-unverified | 65.21.67.207 | expected 10.40.0.2/24 | remote-unverified | private unreachable |
| C | Qwen AI | remote-unverified | remote-unverified | 5.9.108.250 | 10.40.0.4/24 | remote-unverified | private ICMP and SSH TCP reachable |
| D | Marketplace/Postiz/Scraper | remote-unverified | remote-unverified | 49.12.145.107 | not registered | remote-unverified | public 22/80/443 reachable |

Middleware uses parent `enp41s0`, VLAN interface `enp41s0.4001`, VLAN ID 4001,
address 10.40.0.1/24, and MTU 1400. Its public default route remains via
65.109.65.129. NTP is synchronized and the local timezone is
America/Santo_Domingo.

Docker, SSH, and systemd-timesyncd are active. Public host listeners are limited
to SSH, HTTP, and HTTPS; database, Redis, NATS, monitoring, Odoo, n8n, IAM, and
middleware application ports are loopback-only or Docker-network-only.

Remote inventory gate: each remote local Codex session must export hostname,
`/etc/os-release`, kernel, addresses, routes, link/VLAN details, MTU, firewall,
listeners, Docker networks, systemd failures, resolver, NTP, certificate
metadata, and monitoring health using the runbook.

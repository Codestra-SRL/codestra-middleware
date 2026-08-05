# Network Validation Runbook

Run locally in each authorized zone. Do not add cross-host root trust and do
not print secrets.

1. Record `hostname -f`, `/etc/os-release`, `uname -r`, `ip -br address`,
   `ip -4 route`, `ip -6 route`, and `ip -d link`.
2. Record `ss -lntup`, firewall status, `docker network ls`, unhealthy
   containers, failed systemd units, `resolvectl status`, and `timedatectl`.
3. Verify VLAN 4001, the registered private address, MTU 1400, and absence of a
   private default gateway. Run duplicate-address detection before changes.
4. Probe only registered peers with three ICMP samples, `tracepath`, and the
   allowlisted TCP ports in `NETWORK_PORTS.md`.
5. Validate TLS with the required SNI and CA; record only certificate subject,
   issuer, serial, validity, and SHA-256 fingerprint.
6. Run a bounded iperf3 test only after a temporary authenticated endpoint and
   rate/window are separately approved. Remove it immediately afterward.
7. Return sanitized evidence to middleware for matrix consolidation.

## VICIdial recovery sequence

On 65.21.67.207, inspect before changing anything: confirm `10.40.0.2/24` is
present on VLAN 4001, link is UP, MTU is 1400, ARP learns 10.40.0.1, and local
firewall permits the existing allowlisted contracts. Preserve public routes,
SSH, Asterisk, carriers, trunks, dial plans, and campaigns. Any network change
requires a backup and automatic rollback timer.

## Acceptance

All four local reports must agree on addresses, MTU, routes, DNS, certificate
identity, and allowed ports. Every required directed edge must pass; every
forbidden edge must fail closed. Only then may private connectivity be marked
healthy.

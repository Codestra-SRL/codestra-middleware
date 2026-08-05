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

Copy/paste read-only collection for the VICIdial local Codex session:

```bash
set -euo pipefail
test "$(curl --fail --silent --max-time 10 https://api.ipify.org)" = "65.21.67.207"
hostname -f
. /etc/os-release; printf 'OS=%s %s\n' "$NAME" "$VERSION_ID"
uname -r
ip -br address
ip -d link
ip -4 route
ip -6 route
ip route get 10.40.0.1
ping -n -c 5 -W 1 10.40.0.1 || true
ip neigh show
ss -H -lntup
ufw status verbose || true
nft list ruleset
timedatectl show -p NTPSynchronized -p Timezone
systemctl --failed --no-pager
docker network ls 2>/dev/null || true
```

Return the output with secrets and private-key material excluded. If
10.40.0.2/24 or VLAN 4001 is absent, prepare a Netplan backup and rollback
timer, but do not apply a network change until the local session has verified
the physical parent and current public default route.

## Acceptance

All four local reports must agree on addresses, MTU, routes, DNS, certificate
identity, and allowed ports. Every required directed edge must pass; every
forbidden edge must fail closed. Only then may private connectivity be marked
healthy.

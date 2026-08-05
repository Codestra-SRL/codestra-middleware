# Connectivity rollback

Server A's pre-change rollback directory is:

`/root/codestra-network-rollbacks/20260805T151200Z`

It is root-owned mode 0700 and contains SSH, authorized-key, UFW, Netplan,
systemd-networkd, address, and route evidence.

To roll back Server A SSH hardening from console:

1. Restore the saved `sshd_config` and `sshd_config.d` atomically.
2. Run `sshd -t`.
3. Reload `ssh` only after validation.
4. Confirm TCP/22 listeners and an existing approved operator session.

Network and firewall files were not changed during this pass. Do not restore
them merely because a remote server is unreachable. Diagnose the destination
and vSwitch first. Never alter the public default route as part of rollback.

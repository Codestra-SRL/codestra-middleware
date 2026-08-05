# TLS and Certificate Inventory

Public DNS for middleware services resolves to 65.109.65.169. Successful TLS
handshakes were observed for `api`, `auth`, `crm`, `n8n`, `bridge-staging`, and
`phone` under `codestra.agency`, plus `monitoring.codestra.co`. Their current
certificates expire between 2026-10-18 and 2026-10-25.

The private endpoint uses SNI `middleware.internal.codestra.agency`. Its leaf
certificate expires 2027-08-23, is issued by the Codestra Private Integration
Root CA, and had SHA-256 fingerprint:

`AA:62:B0:8E:9B:42:7E:6B:F3:84:10:C0:D1:94:D8:B8:C5:79:59:32:62:6C:17:2C:F1:54:3D:E5:69:0E:26:94`

Private TLS requires an approved client CA. A no-certificate handshake cannot
authorize the private route. Certificate contents, private keys, HMAC values,
and signatures were not recorded. Remote-zone TLS inventories remain pending
their local sessions.
